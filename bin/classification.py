#!/usr/bin/env python3

# extract the AddressBase product classification scheme into a lookup CSV
# with an explicit hierarchy: each code's PARENT is the nearest ancestor
# code that actually appears in the scheme (some tertiary levels are
# unused placeholders, e.g. "LB99AV"'s parent is "LB", not "LB99")

import csv
import sys
from zipfile import ZipFile

scheme_path = "./cache/addressbase-product-classification-scheme.zip"
scheme_member = "addressbase-product-classification-scheme.csv"
out_path = "./data/addressbase-classification.csv"

# a code's ancestor prefixes, longest first: PP SS TT QQ -> try PPSSTT, PPSS, P
prefix_lengths = {2: [1], 4: [2, 1], 6: [4, 2, 1]}


def parent_of(code, codes):
    for length in prefix_lengths.get(len(code), []):
        prefix = code[:length]
        if prefix in codes:
            return prefix
    return ""


def read_scheme(path, member):
    with ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith(member))
        with z.open(name) as f:
            return list(csv.DictReader(line.decode("utf-8-sig") for line in f))


if __name__ == "__main__":
    rows = read_scheme(scheme_path, scheme_member)
    codes = {row["Concatenated"] for row in rows}

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["CLASSIFICATION_CODE", "DESCRIPTION", "PARENT"])
        for row in rows:
            code = row["Concatenated"]
            writer.writerow([code, row["Class_Desc"], parent_of(code, codes)])
