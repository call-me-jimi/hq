****************************
Installation & Configuration
****************************

Installation
============

In order to install the hq package please follow the steps:

Create virtual environment
--------------------------

change to your hq package::
    
  cd YOUR_HQ_PATH

create virtual environment and create file which has to be sourced in order to use this application ::
    
  make

activate virtual environment (environmental variables :obj:`HQPACKAGE`, :obj:`HQPATH` and
:obj:`HQ_VE_PATH will` be set)::
    
   source .hqrc
    

Install mysql server (optional)
-------------------------------

If no mysql server is installed on your system or you do not have access to it you may install your
own mysql server and client. 

install mysql server (in :file:`$HQ_VE_PATH/usr/mysql-MYSQL_VERSION-hqdb`, where
:obj:`MYSQL_VERSION` has to be replaced by the installed mysql version, e.g., 5.6.22)::
  
  cd $HQPACKAGE
  make sql

create database::
  
  cd $HQ_VE_PATH/usr/mysql-MYSQL_VERSION-hqdb
  scripts/mysql_install_db --defaults-file=hqdb.cnf

start mysql server::
  
  bin/mysqld_safe --defaults-file=hqdb.cnf

assumed the following passwords for mysql-root and hq-admin::
  
  root:mYSqlTmdB
  hqadmin:mYsqLTmdB

create password for root::
  
  bin/mysqladmin --defaults-file=hqdb.cnf -u root password 'mYSqlTmdB'

connect to database::
  
  bin/mysql --defaults-file=hqdb.cnf --user=root -p

drop anonymous user in order to be able to connect with ``bin/mysql --host=HOST --port=PORT --user=USER --database=DATABASE -p``
see: |stackoverflow10299148|::

  mysql> DROP USER ''@'localhost';
  mysql> DROP USER ''@'<YOUR HOST>';

create user::
  
  mysql> CREATE USER 'hqadmin'@'%' IDENTIFIED BY 'mYsqLTmdB';

create database::

  mysql> CREATE DATABASE IF NOT EXISTS hqdb;
  mysql> GRANT ALL PRIVILEGES ON hqdb.* TO 'hqadmin'@'%' WITH GRANT OPTION;

stop server::
  
  bin/mysqladmin --defaults-file=hqdb.cnf -u root -p shutdown

connect as hqadmin to mysql server::

  bin/mysql --host=localhost --port=2114 --database=hqdb --user=hqadmin -p

Setup hQ
--------

install python packages::
  
  export PATH=$PATH:$HQ_VE_PATH/usr/mysql-${MYSQL_VERSION}-hqdb/bin
  pip install -r $HQPACKAGE/hqConf/requirements.txt

(option) create documentation (using sphinx) in ``$HQPACKAGE/doc/html``::

  make doc

(optional) create a frozen version of several python programs with freeze. Modify and execute
script::
      
  cd $HQPATH
  python scripts/makeFreezedVersion.py

For each program all necessary python libraries are copied to a single directory and a binary is
created. Therefore a load of python libraries over an intranet is not anymore necessary and it makes
the execution faster. Modify the wrapper script bin/hqwrapper in the directory bin/ in order to
invoke the compiled version respectively.

set permissions of wrapper scripts in bin/ that every user can execute it::

  cd $HQPATH/bin
  chmod g+x *
  
add users who are allowed to use the hQ into::

  etc/users

with the format::

  USERNAME ROLE1,ROLE2

in each row a user with his/her user roles.

.. note::

   In the current implementation roles are not considered, but each user has to have at least one role

configure computer cluster by given information about each host in the cluster in tab delimited file::

  etc/cluster.tab

set database configuration::

  etc/hq-db.cfg

create tables in database::

  hq-dbadmin --create-tables --add-standard-entries

start hq-server (if you sourced the file :file:`.hqrc`, the :file:`HQPATH/bin` has been added to the
environmental variable :file:`$PATH`.)::

  hq-server


.. |stackoverflow10299148| raw:: html

   <a href="http://stackoverflow.com/questions/10299148/mysql-error-1045-28000-access-denied-for-user-billlocalhost-using-passw" target='_blank'>stackoverflow</a>
