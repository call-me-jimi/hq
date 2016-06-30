*****
Usage
*****

In order to use the following command source the package file::

  cd YOUR_HQ_PATH
  source .hqrc

as admin
========

Start hq-server::

  hq-server

Get help::

  hq-admin help

Get info/status of hq-server::

  hq-admin info
  hq-admin status

Get overview of cluster::

  hq-admin lscluster
      
Activate host by name::

  hq-admin activatehost:localhost

Activate cluster::

  hq-admin activate

as user
=======

A user has to use the client to get user specific information::

  hq-client --help   
  hq-client details
  hq-client status

Send job to cluster::

  hq-submit --help   
  hq-submit "sleep 42"


