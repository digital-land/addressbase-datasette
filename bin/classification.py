#!/usr/bin/env python3

# extract classification code lookups from the AddressBase product
# classification scheme zip into a single CSV covering all three schemes
# used by AddressBase Premium's CLASSIFICATION.CLASS_SCHEME column:
#
# - "AddressBase Premium Classification Scheme": hierarchical codes, with
#   an explicit PARENT - the nearest ancestor code that actually appears
#   in the scheme (some tertiary levels are unused placeholders, e.g.
#   "LB99AV"'s parent is "LB", not "LB99")
# - "VOA Primary Description" and "VOA Special Category": flat VOA codes
#   (no hierarchy, so PARENT is always empty). The same code string can
#   mean different things in different schemes (e.g. "CA" is
#   "Agricultural" in the AddressBase scheme but "Advertising Right and
#   premises" as a VOA Primary Description code), so CLASSIFICATION_CODE
#   alone isn't a unique key across schemes - CLASS_SCHEME is part of it.

import csv
from zipfile import ZipFile

scheme_path = "./cache/addressbase-product-classification-scheme.zip"
scheme_member = "addressbase-product-classification-scheme.csv"
voa_member = "voa-primary-description-scat-lookup.csv"
out_path = "./data/addressbase-classification.csv"

addressbase_scheme = "AddressBase Premium Classification Scheme"
voa_scat_scheme = "VOA Special Category"
voa_primary_scheme = "VOA Primary Description"

# a code's ancestor prefixes, longest first: PP SS TT QQ -> try PPSSTT, PPSS, P
prefix_lengths = {2: [1], 4: [2, 1], 6: [4, 2, 1]}


def parent_of(code, codes):
    for length in prefix_lengths.get(len(code), []):
        prefix = code[:length]
        if prefix in codes:
            return prefix
    return ""


def read_member(path, member):
    with ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(member))
        with z.open(name) as f:
            return [line.decode("utf-8-sig") for line in f]


def addressbase_rows():
    rows = list(csv.DictReader(read_member(scheme_path, scheme_member)))
    codes = {row["Concatenated"] for row in rows}
    for row in rows:
        code = row["Concatenated"]
        yield (addressbase_scheme, code, row["Class_Desc"], parent_of(code, codes))


def voa_rows():
    # the file has a 3-line title/description preamble before the real header
    lines = read_member(scheme_path, voa_member)[3:]

    scat = {}
    primary = {}
    for row in csv.DictReader(lines):
        scat_code = row["SCat Code"].strip().zfill(3)
        scat[scat_code] = row["SCat Code Description"].strip()

        primary_code = row["Primary Description Code"].strip()
        if primary_code:
            primary[primary_code] = row["Primary Description"].strip()

    for code, desc in sorted(scat.items()):
        yield (voa_scat_scheme, code, desc, "")
    for code, desc in sorted(primary.items()):
        yield (voa_primary_scheme, code, desc, "")


if __name__ == "__main__":
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["CLASS_SCHEME", "CLASSIFICATION_CODE", "DESCRIPTION", "PARENT"])
        writer.writerows(addressbase_rows())
        writer.writerows(voa_rows())
