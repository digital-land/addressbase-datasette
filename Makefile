.PHONY: init all clean clobber prune server
.DELETE_ON_ERROR:
export SPATIALITE_EXTENSION:=/usr/lib/x86_64-linux-gnu/mod_spatialite.so

DB=addressbase.sqlite3

AddressBase_ZIP=cache/AB76GB_CSV.zip
AddressBase_HEADERS_CSV=cache/addressbase-premium-header-files.zip
Classification_ZIP=cache/addressbase-product-classification-scheme.zip
Classification_CSV=data/addressbase-classification.csv

all:	$(DB) $(Classification_CSV)

$(Classification_CSV):	$(Classification_ZIP) bin/classification.py
	@mkdir -p data
	python3 bin/classification.py

server:	$(DB)
	datasette serve $(DB) \
	--config sql_time_limit_ms:50000 \
	--load-extension $(SPATIALITE_EXTENSION) \
	--metadata datasette/metadata.json \
	--template-dir datasette/templates/

$(DB):	$(DB_DATA) bin/load.py
	@rm -f $@
	python3 bin/load.py $@

init:
	pip3 install -r requirements.txt

clobber:
	rm -f $(DB) $(Classification_CSV)

clean:	clobber
	rm -rf ./var

prune:	clean
	rm -rf ./cache
