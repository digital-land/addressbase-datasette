#!/usr/bin/env python3

# unpack AddressBase Premium ZIP into a sqlite3 database

import os
import csv
import sqlite3
import threading
import queue
from io import TextIOWrapper
from zipfile import ZipFile


header_path = "./cache/addressbase-premium-header-files.zip"
addressbase_path = "./cache/AB76GB_CSV.zip"
db_path = "./addressbase.sqlite3"
cursor = None

# create table in order of dependencies
table_order = ["STREET", "BLPU"]

primary_keys = {
    "BLPU": "UPRN",
    "STREET": "USRN",
    "LPI": "LPI_KEY",
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
QUEUE_SIZE = 20  # batches buffered between parser thread and db writer


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


def parse_addressbase(path, q):
    # runs in a background thread: decompresses and parses CSV rows into
    # batches while the main thread is free to be blocked inside sqlite3,
    # since the sqlite3 C extension releases the GIL during execute calls
    buffers = {}

    def unpack_addressbase(path, reader):
        print(path)
        for row in reader:
            record = row[0]
            buffer = buffers.setdefault(record, [])
            buffer.append(row)
            if len(buffer) >= BATCH_SIZE:
                q.put((record, buffer))
                buffers[record] = []

    try:
        zipfile(path, unpack_addressbase)

        for record, buffer in buffers.items():
            if buffer:
                q.put((record, buffer))

        q.put(None)  # sentinel: parsing is done
    except Exception as e:
        q.put(e)


def load_addressbase(path):
    q = queue.Queue(maxsize=QUEUE_SIZE)
    # daemon: if the main thread raises, don't hang the process waiting
    # on a parser blocked writing to a queue nobody is draining anymore
    parser = threading.Thread(target=parse_addressbase, args=(path, q), daemon=True)
    parser.start()

    while True:
        item = q.get()
        if item is None:
            break
        if isinstance(item, Exception):
            raise item
        record, batch = item
        cursor.executemany(headers[record]["sql"], batch)

    parser.join()


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
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = OFF")
    cursor.execute("PRAGMA locking_mode = EXCLUSIVE")
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
        connection.execute(
            f'CREATE {unique}INDEX IF NOT EXISTS {idx} ON {i["table"]} ({i["col"]})'
        )


if __name__ == "__main__":
    connection = open_connection(db_path)

    zipfile(header_path, unpack_headers)
    create_tables(connection)

    cursor = create_cursor(connection)
    load_addressbase(addressbase_path)

    commit(connection)

    create_indexes(connection)

    connection.close()
    exit(0)
