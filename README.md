HQ
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
jobs of users and sends jobs to vacant hosts of the cluster, if possible. A hq-user-server is
automatically invoked with the user's permissions. The user sends all his requests (via a client or
programmatically) to his own hq-user-server, which in turn communicates with the hq-server. A
hq-exec-server is invoked automatically with the user's permission on each host. The hq-exec-server
is responsible for executing the user's jobs. The hq-server and hq-exec-server store and modify all
information about jobs, hosts, users in the underlying database. Other clients/applications could
access this database to retreive information about jobs and the cluster.


System requirements
===================

- Unix system with a python installation
- One or more computers with one or more cores
- Access to the home file system on each host (it is not absolutly necessary. see below)


Installation & Configuration
============================

In order to install the hq package please follow the configuation steps:

** Create virtual environment

# change to your hq path
cd <YOUR_HQ_PATH>

# create virtual environment, install mysql client and create file which has to be sourced in order
# to use this application 
make

# activate virtual environment (environmental variables HQPATH and HQ_VE_PATH will be set)
source .hqrc

## Install mysql server
cd $HQPATH
make sql

## create database
cd $MYSQL_INSTANCE
scripts/mysql_install_db --defaults-file=$MYSQL_INSTANCE/hqdb.cnf

## start server
bin/mysqld_safe --defaults-file=$MYSQL_INSTANCE/hqdb.cnf

# password
root:mYSqlTmdB
hqadmin:mYsqLTmdB

## create password for root
bin/mysqladmin --defaults-file=$MYSQL_INSTANCE/hqdb.cnf -u root password 'mYSqlTmdB'

# connect to database (on database01)
bin/mysql --defaults-file=$MYSQL_INSTANCE/hqdb.cnf --user=root -p

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
bin/mysqladmin --defaults-file=$MYSQL_INSTANCE/hqdb.cnf -u root -p shutdown

# connect as hqadmin to mysql server
bin/mysql --host=localhost --port=2114 --database=hqdb --user=hqadmin -p


# install python packages
export PATH=$PATH:$MYSQL_INSTANCE/bin
pip install -r <YOUR_HQ_PATH>/hqConf/requirements.txt







2. (optional) Create a frozen version of several python programs with freeze. Modify and execute script
      
      cd <HQPATH>
      python scripts/makeFreezedVersion.py

For each program all necessary python libraries are copied to a single directory and a binary is
created. Therefore a load of python libraries over an intranet is not anymore necessary and it makes
the execution faster. Modify the wrapper script bin/hqwrapper in the directory bin/ in order to
invoke the compiled version respectively.

3. Set permissions of wrapper scripts in bin/ that every user can execute it.

4. Add users who are allowed to use the Hq into

      etc/users

Format:

  <Username> <ROLE1>,<ROLE2>

in each row a user with his/her user roles.

In the current implementation roles are not considered, but each user has to have at least one role

5. Configure computer cluster by given information about each host in the cluster in tab delimited file

     etc/cluster.tab

6. Start hq-server (if you sourced the file .hqrc, the HQPATH/bin has been added to the
environmental variable $PATH.)

      hq-server


Several Commands
================

Start hq-server

      hq-server

Get help

      hq-admin help

Get details/status of hq-server

      hq-admin details
      hq-admin status

Activate computer (if localhost is one of your hosts defined in etc/cluster.tab)

      hq-admin activatehost:localhost

Activate cluster

      hq-admin activate

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

