HQPACKAGE=$(shell pwd)
VE_PATH=$(HQPACKAGE)/hqVE
SRC_PATH=$(HQPACKAGE)/src
DOC_PATH=$(HQPACKAGE)/doc
SPHINX_PATH=$(HQPACKAGE)/sphinx

all: ve rc

ve:
	virtualenv hqVE

rc:
	# generate a source file
	# necessary enironmental variables are set within this source files
	echo 'export HQPACKAGE=$(HQPACKAGE)'  > .hqrc
	echo 'export HQPATH=$(HQPACKAGE)/hq'  >> .hqrc
	echo 'export HQ_VE_PATH=$(HQPACKAGE)/hqVE'  >> .hqrc
	echo ''  >> .hqrc
	echo 'source $(HQ_VE_PATH)/bin/activate' >> .hqrc
	echo ''  >> .hqrc
	echo 'export PATH=$(HQPATH)/bin:$$PATH' >> .hqrc
	echo 'export PYTHONPATH=$(HQPACKAGE):$$PYTHONPATH' >> .hqrc

sql:
	# install mysql (required by python package MySQLdb)
	cd $(VE_PATH) && \
	mkdir -p src && \
	cd src && \
	wget http://dev.mysql.com/get/Downloads/MySQL-5.6/mysql-5.6.22.tar.gz && \
	tar xzvf mysql-5.6.22.tar.gz && \
	cd mysql-5.6.22 && \
	cmake -DCMAKE_INSTALL_PREFIX=$(VE_PATH)/usr/mysql-5.6.22-hqdb && \
	make -j 2 install && \
	sed "s:{mysqlpath}:$(VE_PATH)/usr/mysql-5.6.22-hqdb:" $(HQPACKAGE)/hqConf/hqdb.cnf > $(VE_PATH)/usr/mysql-5.6.22-hqdb/hqdb.cnf
doc:
	# Create documentation if not existing
	# If existing, update
	if [ -d $(SPHNIX_PATH)/_static ]; then \
		rm -rf $(SPHINX_PATH)/*.png; \
		rm -rf $(SPHINX_PATH)/*.rst; \
		rm -rf $(DCO_PATH)/html; \
	else \
		mkdir -p $(SPHINX_PATH); \
		sphinx-quickstart -q -p'hQ' -a'h.h.' -v0.9 --suffix='.rst' --no-batchfile  --ext-autodoc --ext-intersphinx --ext-viewcode $(SPHINX_PATH); \
		sed -i -e 's/^html_theme.*/html_theme = "sphinxdoc"/' $(SPHINX_PATH)/conf.py; \
		echo "" >> $(SPHINX_PATH)/conf.py; \
		echo "def setup(app):" >> $(SPHINX_PATH)/conf.py; \
		echo "    app.add_javascript('copybutton.js')" >> $(SPHINX_PATH)/conf.py; \
	fi

	# copy source files to sphinx folder
	find $(SRC_PATH)/rst -name "*rst" -type f -exec cp {} $(SPHINX_PATH) \;

	# copile documentation as html
	cd $(SPHINX_PATH) && $(MAKE) html

	# copy generated files to doc folder
	cp -r $(SPHINX_PATH)/_build/html $(DOC_PATH)/
	cp $(SRC_PATH)/js/* $(DOC_PATH)/html/_static

	#
	# Documentation has been create. Please go to: $(DOC_PATH)/html/index.html
	#
rmdoc:
	# remove everything except the directories and source files
	rm -rf $(SPHINX_PATH)/conf.py
	rm -rf $(SPHINX_PATH)/*.png
	rm -rf $(SPHINX_PATH)/*.rst
	rm -rf $(SPHINX_PATH)/_static
	rm -rf $(SPHINX_PATH)/_build
	rm -rf $(SPHINX_PATH)/_templates
	rm -rf $(SPHINX_PATH)/Makefile
	rm -rf $(DOC_PATH)/html

.PHONY: all ve rc sql doc
