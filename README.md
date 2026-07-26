Load AddressBase into sqlite3 database and explore it using datasette

# Data sources

1. Order a copy of [OS AddressBase Premium](https://www.ordnancesurvey.co.uk/business-government/products/addressbase-premium).
2. Download the CSV version and save it as `cache/AB76GB_CSV.zip`
3. Download the [CSV header files](https://docs.os.uk/os-downloads/products/addresses-and-names-portfolio/addressbase-premium/addressbase-premium-downloads#addressbase-premium-header-files) and save them as `cache/addressbase-premium-header-files.zip`
4. Download the [Classification codes](https://docs.os.uk/os-downloads/products/addresses-and-names-portfolio/addressbase-fundamentals/classification-scheme) and save the as `cache/addressbase-product-classification-scheme.zip`

# Building the guidance and database

We recommend working in [virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/) before installing the python dependencies:

    $ make init
    $ make

Note that building the database and indexes can take more than an hour on an modern laptop.
You can explore the data in a browser using datasette:

    $ make serve

# Licence

The software in this project is open source and covered by the [LICENSE](LICENSE) file.

Otherwise all content and data in this repository is
[© Crown copyright](http://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/copyright-and-re-use/crown-copyright/)
and available under the terms of the [Open Government 3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) licence.
