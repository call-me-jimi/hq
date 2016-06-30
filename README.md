hQ
==

hq is an open source infrastructure software for distributing and managing the execution of
calculation jobs in a Unix computer cluster environment. hq was designed to control a set of
hosts even if you are not the administrator of the system. The hosts are embedded in a Unix
environment and the user's home directories are mounted on each host. The hosts may have different
numbers of CPUs/cores and operating systems. Keep in mind that a user should be able to log into
each host via ssh. However, users should use hq-submit to submit calculation jobs to the cluster to
avoid an overload of the hosts and to a proper scheduling. Jobs which are under the control of hq
are executed on a host of the computer cluster with the rights of the respective user to ensure that
the executing jobs have the permission to access the user's files.

hq package consists of several servers, hq-server, hq-user-server, and hq-exec-server, which
communicate with each other. Furthermore, clients may send requests to one of these servers. Behind
all servers there is a MySQL database. The main server, hq-server, stores detailed information about
jobs of users and sends jobs to vacant hosts of the cluster. A hq-user-server is automatically
invoked at the first use of hq-submit or hq-client with the user's permissions. The user sends all
requests (via hq-submit or proxy server implemented in the module hServerProxy) to his own
hq-user-server, which in turn communicates with the hq-server. A hq-exec-server is invoked
automatically with the user's permission on each host. The hq-exec-server is responsible for
executing the user's jobs. The hq-server and hq-exec-server store and modify all information about
jobs, hosts, users in the underlying database. Other clients/applications could access this database
to retreive information about jobs and the cluster.


System requirements
===================

- Unix system with a python installation
- One or more computers with one or more cores
- Access to the home file system on each host (it is not absolutly necessary. see below)


Installation & Configuration
============================

In order to install the hq package please follow the configuation steps:

** Create virtual environment

# change to your hq package
cd <YOUR_HQ_PATH>

# create virtual environment and create file which has to be sourced in order
# to use this application 
make

# activate virtual environment (environmental variables HQPATH and HQ_VE_PATH will be set)
source .hqrc

** Install mysql server (optional) 

# install mysql server (in $HQ_VE_PATH/usr/mysql-${MYSQL_VERSION}-hqdb)
cd $HQPATH
make sql

# create database
cd $HQ_VE_PATH/usr/mysql-${MYSQL_VERSION}-hqdb
scripts/mysql_install_db --defaults-file=hqdb.cnf

# start server
bin/mysqld_safe --defaults-file=hqdb.cnf

# assumed the following passwords for mysql-root and hq-admin.
root:mYSqlTmdB
hqadmin:mYsqLTmdB

# create password for root
bin/mysqladmin --defaults-file=hqdb.cnf -u root password 'mYSqlTmdB'

# connect to database (on database01)
bin/mysql --defaults-file=hqdb.cnf --user=root -p

# drop anonymous user in able to connect with bin/mysql --host=<HOST> --port=<PORT> --user=<USER> --database=<DATABASE> -p
# see: http://stackoverflow.com/questions/10299148/mysql-error-1045-28000-access-denied-for-user-billlocalhost-using-passw
mysql> DROP USER ''@'localhost';
mysql> DROP USER ''@'<YOUR HOST>';

# create user
mysql> CREATE USER 'hqadmin'@'%' IDENTIFIED BY 'mYsqLTmdB';

# create database
mysql> CREATE DATABASE IF NOT EXISTS hqdb;
mysql> GRANT ALL PRIVILEGES ON hqdb.* TO 'hqadmin'@'%' WITH GRANT OPTION;

# stop server
bin/mysqladmin --defaults-file=hqdb.cnf -u root -p shutdown

# connect as hqadmin to mysql server
bin/mysql --host=localhost --port=2114 --database=hqdb --user=hqadmin -p

** Setup hq

# install python packages
export PATH=$PATH:$MYSQL_INSTANCE/bin
pip install -r <YOUR_HQ_PATH>/hqConf/requirements.txt

# (option) create documentation (using sphinx) in <YOUR_HQ_PATH>/doc/html

  make doc

# (optional) create a frozen version of several python programs with freeze. Modify and execute
# script
      
      cd <HQPATH>
      python scripts/makeFreezedVersion.py

For each program all necessary python libraries are copied to a single directory and a binary is
created. Therefore a load of python libraries over an intranet is not anymore necessary and it makes
the execution faster. Modify the wrapper script bin/hqwrapper in the directory bin/ in order to
invoke the compiled version respectively.

# set permissions of wrapper scripts in bin/ that every user can execute it.

# add users who are allowed to use the Hq into

      etc/users

Format:

  <Username> <ROLE1>,<ROLE2>

in each row a user with his/her user roles.

In the current implementation roles are not considered, but each user has to have at least one role

# configure computer cluster by given information about each host in the cluster in tab delimited file

     etc/cluster.tab

# set database configuration

     etc/hq-db.cfg

# create tables in database

     hq-dbadmin --create-tables --add-standard-entries

# start hq-server (if you have sourced the file ``.hqrc``, the ``HQPATH/bin`` has been added to the
# environmental variable ``$PATH``.)

      hq-server


Several Commands
================

** as admin

Start hq-server

      hq-server

Get help

      hq-admin help

Get info/status of hq-server

      hq-admin info
      hq-admin status

Get overview of cluster

      hq-admin lscluster
      
Activate host by name

      hq-admin activatehost:localhost

Activate cluster

      hq-admin activate

** as user

A user has to use the client to get user specific information

      hq-client --help   
      hq-client details
      hq-client status

Send job to cluster

      hq-submit --help   
      hq-submit "sleep 42"




Changelog
=========

current GIT version
-------------------


Since 0.9
---------
initial import

