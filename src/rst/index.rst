Welcome to hQ's documentation!
==============================

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



Reference Manual
================

.. toctree::
   :maxdepth: 2

   installation
   usage
   hq




Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

