Experiments with loading [OS AddressBase Premium](https://www.ordnancesurvey.co.uk/business-government/tools-support/addressbase-premium-support) into [datasette](https://github.com/simonw/datasette).

# Data

You need a copy of AddressBase zip file, which is 350 million rows of CSV.

The resulting sqlite database is ~7 Gigabytes, with ~33 million UPRNs.

# Building

We recommend working in [virtual environment](http://docs.python-guide.org/en/latest/dev/virtualenvs/) before installing the python dependencies:

    $ make init
    $ make

# Licence

The software in this project is open source and covered by LICENSE file.

Individual datasets copied into this repository may have specific [copyright](collection/attribution/) and [licensing](collection/licence/),
otherwise all content and data in this repository is
[© Crown copyright](http://www.nationalarchives.gov.uk/information-management/re-using-public-sector-information/copyright-and-re-use/crown-copyright/)
and available under the terms of the [Open Government 3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) licence.
