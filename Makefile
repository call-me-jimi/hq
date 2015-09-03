HQPATH=$(shell pwd)
VE_PATH=$(HQPATH)/hqVE

all: ve rc

ve:
	virtualenv hqVE

rc:
	# generate a source file
	# necessary enironmental variables are set within this source files
	echo 'export HQPACKAGE=$(HQPATH)'  > .hqrc
	echo 'export HQPATH=$(HQPATH)/hq'  >> .hqrc
	echo 'export HQ_VE_PATH=$(HQPATH)/hqVE'  >> .hqrc
	echo ''  >> .hqrc
	echo 'source $(HQPATH)/hqVE/bin/activate' >> .hqrc
	echo ''  >> .hqrc
	echo 'export PATH=$(HQPATH)/hq/bin:$$PATH' >> .hqrc
	echo 'export PYTHONPATH=$(HQPATH):$$PYTHONPATH' >> .hqrc

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
	sed "s:{mysqlpath}:$(VE_PATH)/usr/mysql-5.6.22-hqdb:" $(HQPATH)/hqConf/hqdb.cnf > $(VE_PATH)/usr/mysql-5.6.22-hqdb/hqdb.cnf

.PHONY: all ve rc sql
