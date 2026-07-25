#!/usr/bin/env python3

# unpack AddressBase Premium ZIP into a sqlite3 database

import os
import csv
import sqlite3
import multiprocessing as mp
from io import TextIOWrapper
from zipfile import ZipFile


header_path = "./cache/addressbase-premium-header-files.zip"
addressbase_path = "./cache/AB76GB_CSV.zip"
classification_path = "./data/addressbase-classification.csv"
db_path = "./addressbase.sqlite3"
cursor = None

# create table in order of dependencies
table_order = ["STREET", "BLPU"]

primary_keys = {
    "BLPU": "UPRN",
    "STREET": "USRN",
    "LPI": "LPI_KEY",
    # CLASSIFICATION_CODE isn't an AddressBase Premium header-driven table
    # (it's built separately by load_classification_code below), but adding
    # its pk here makes CLASSIFICATION.CLASSIFICATION_CODE pick up a
    # foreign key + index via the generic mechanism below
    "CLASSIFICATION_CODE": "CLASSIFICATION_CODE",
}

foreign_keys = {v: k for k, v in primary_keys.items()}

col_types = {
    "UPRN": "INTEGER",
    "USRN": "INTEGER",
    "UDPRN": "INTEGER",
    "LOCAL_CUSTODIAN_TYPE": "INTEGER",
}

headers = {}
indexes = {}

BATCH_SIZE = 10000
QUEUE_SIZE = 20  # batches buffered between parser workers and db writer
WORKERS = max(1, (os.cpu_count() or 2) - 1)  # leave a core for the db writer
COMMIT_INTERVAL = 200  # batches per commit (~2M rows) to bound WAL growth


def unpack_headers(path, reader):
    # header filenames are in the format "cache/Record_10_HEADER_Header.csv"
    (_, record, table, _) = path.split("_")
    fieldnames = next(reader)
    header = {
        "record": record,
        "table": table,
        "fieldnames": fieldnames,
    }
    headers[record] = header


def worker_parse_addressbase(path, member_names, q):
    # runs in a worker process: each worker decompresses and parses its own
    # share of the zip's member files, in parallel across cpu cores, and
    # sends batches of rows back to the single db-writer process over a
    # shared queue (sqlite only allows one writer, so writing stays serial)
    buffers = {}
    try:
        with ZipFile(path) as z:
            for name in member_names:
                print(name)
                with z.open(name, "r") as infile:
                    reader = csv.reader(TextIOWrapper(infile, "utf-8", newline=""))
                    for row in reader:
                        record = row[0]
                        buffer = buffers.setdefault(record, [])
                        buffer.append(row)
                        if len(buffer) >= BATCH_SIZE:
                            q.put((record, buffer))
                            buffers[record] = []

        for record, buffer in buffers.items():
            if buffer:
                q.put((record, buffer))
    except Exception as e:
        q.put(e)
    finally:
        q.put(None)  # sentinel: this worker is done


def load_addressbase(path):
    with ZipFile(path) as z:
        member_names = [i.filename for i in z.infolist() if not i.is_dir()]

    if not member_names:
        return

    # spread members round-robin across workers; parallelism is capped by
    # the number of files in the zip, not by cpu count
    workers = min(WORKERS, len(member_names))
    chunks = [member_names[i::workers] for i in range(workers)]

    q = mp.Queue(maxsize=QUEUE_SIZE)
    procs = [
        mp.Process(target=worker_parse_addressbase, args=(path, chunk, q), daemon=True)
        for chunk in chunks
    ]
    for p in procs:
        p.start()

    error = None
    remaining = len(procs)
    batches_since_commit = 0
    while remaining > 0:
        item = q.get()
        if item is None:
            remaining -= 1
        elif isinstance(item, Exception):
            error = error or item
        else:
            record, batch = item
            cursor.executemany(headers[record]["sql"], batch)
            batches_since_commit += 1
            # commit periodically instead of one giant transaction spanning
            # the whole load: keeps the WAL bounded and limits how much a
            # future failure could lose or corrupt
            if batches_since_commit >= COMMIT_INTERVAL:
                cursor.connection.commit()
                batches_since_commit = 0

    for p in procs:
        p.join()

    if error is not None:
        raise error


def zipfile(path, unpack):
    with ZipFile(path) as z:
        for info in z.infolist():
            with z.open(info.filename, "r") as infile:
                if not info.is_dir():
                    unpack(
                        info.filename,
                        csv.reader(TextIOWrapper(infile, "utf-8", newline="")),
                    )


def open_connection(path):
    connection = sqlite3.connect(path)

    # SpatialLite extension
    connection.enable_load_extension(True)
    connection.load_extension(os.environ["SPATIALITE_EXTENSION"])
    connection.execute("select InitSpatialMetadata(1)")
    return connection



def create_cursor(connection):
    cursor = connection.cursor()
    # WAL + synchronous=NORMAL still produced "database disk image is
    # malformed" on a full load, same as journal_mode=MEMORY before it, so
    # journal mode isn't the (whole) story. Fall back to sqlite's plain
    # defaults - DELETE journal, synchronous=FULL, normal locking - to
    # isolate whether the non-default pragmas are implicated at all.
    cursor.execute("PRAGMA journal_mode = DELETE")
    cursor.execute("PRAGMA synchronous = FULL")
    cursor.execute("PRAGMA temp_store = MEMORY")
    cursor.execute("PRAGMA cache_size = -200000")  # ~200MB page cache
    return cursor


def commit(connection):
    print("committing ..")
    connection.commit()


def add_index(table, col, unique=False):
    idx = f"{table}_{col}_IDX"
    indexes[idx] = {"table": table, "col": col, "unique": unique}


def create_table(connecton, t):
    table = t["table"]
    sql = f"CREATE TABLE {table} ("
    sep = ""
    pk = primary_keys.get(table, None)
    defer_pk_index = False

    for col in t["fieldnames"]:
        col_type = col_types.get(col, "TEXT")

        sql += f"{sep}{col} {col_type}"
        sep = ",\n    "

        if col == pk:
            # INTEGER PRIMARY KEY is a free rowid alias in sqlite3, so it
            # costs nothing extra during load. A non-integer primary key
            # needs a real B-tree index: build it in bulk after loading
            # instead of maintaining it row-by-row on every insert.
            if col_type == "INTEGER":
                sql += " PRIMARY KEY"
            else:
                defer_pk_index = True

    for col in t["fieldnames"]:
        if col in foreign_keys:
            foreign_table = foreign_keys.get(col, None)
            if foreign_table != table:
                sql += f"{sep}FOREIGN KEY ({col}) REFERENCES {foreign_table} ({col})"
                add_index(table, col)
    sql += ")"

    connection.execute(sql)

    if defer_pk_index:
        add_index(table, pk, unique=True)


def insert_sql(t):
    table = t["table"]
    sql = f"INSERT INTO {table} ("

    sep = ""
    for col in t["fieldnames"]:
        sql += f"{sep}{col}"
        sep = ","
    sql += ") VALUES ("

    sep = ""
    for col in t["fieldnames"]:
        sql += f"{sep}?"
        sep = ","
    sql += ")"
    headers[t["record"]]["sql"] = sql


def create_tables(connecton):
    def find(l, key, value):
        return next((i for i, d in enumerate(l) if d.get(key) == value), -1)

    # order tables by foreign key dependencies
    tables = list(headers.values())
    for table in reversed(table_order):
        tables.insert(0, tables.pop(find(tables, "table", table)))

    for t in tables:
        create_table(connection, t)
        insert_sql(t)


def create_indexes(connecton):
    for idx, i in indexes.items():
        unique = "UNIQUE " if i["unique"] else ""
        sql = f'CREATE {unique}INDEX IF NOT EXISTS {idx} ON {i["table"]} ({i["col"]})'
        print(sql)
        connection.execute(sql)


def load_classification_code(connection, path):
    # separate from the AddressBase Premium tables (which already have a
    # CLASSIFICATION table of per-UPRN classification records); this is
    # the code/description/parent lookup built by bin/classification.py.
    # CLASSIFICATION.CLASSIFICATION_CODE has a foreign key into this table
    # (see primary_keys/foreign_keys above), joining the two.
    connection.execute(
        """
        CREATE TABLE CLASSIFICATION_CODE (
            CLASSIFICATION_CODE TEXT PRIMARY KEY,
            DESCRIPTION TEXT,
            PARENT TEXT REFERENCES CLASSIFICATION_CODE (CLASSIFICATION_CODE)
        )
        """
    )
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        connection.executemany(
            "INSERT INTO CLASSIFICATION_CODE "
            "(CLASSIFICATION_CODE, DESCRIPTION, PARENT) VALUES (?, ?, ?)",
            reader,
        )
    connection.commit()


if __name__ == "__main__":
    connection = open_connection(db_path)

    zipfile(header_path, unpack_headers)
    create_tables(connection)

    cursor = create_cursor(connection)
    load_addressbase(addressbase_path)
    commit(connection)

    print("integrity check after load, before indexing ..")
    for row in connection.execute("PRAGMA integrity_check"):
        print(row[0])

    load_classification_code(connection, classification_path)

    create_indexes(connection)

    connection.close()
    exit(0)
