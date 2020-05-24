CACHE_DIR=cache/
VAR_DIR=var/
export SPATIALITE_EXTENSION:=/usr/lib/x86_64-linux-gnu/mod_spatialite.so

# local copy of AddressBase Premium
ADDRESSBASE=$(CACHE_DIR)AB76GB_CSV.zip
ADDRESSBASE_HEADERS=$(CACHE_DIR)addressbase-premium-header-files.zip

serve:	postcode.db
	datasette serve postcode.db --config sql_time_limit_ms:5000 --load-extension=$(SPATIALITE_EXTENSION)

# loading and indexing takes time ..
postcode.db:	$(ADDRESSBASE) $(ADDRESSBASE_HEADERS) bin/load-addressbase.py
	python3 bin/load-addressbase.py $(ADDRESSBASE_HEADERS) $(ADDRESSBASE) $@

# the CSV headers are shipped separately
$(ADDRESSBASE_HEADERS):
	@mkdir -p $(CACHE_DIR)
	curl -qsL 'http://www.os.uk/docs/product-schemas/addressbase-premium-header-files.zip' > $@

init::
	pip3 install --upgrade -r requirements.txt

clean::
	rm -rf $(VAR_DIR)

clobber::
	rm -f postcode.db

prune::
	rm -rf $(CACHE_DIR)

black:
	black .

init::
	pip3 install --upgrade -r requirements.txt

