**********
hQ package
**********

overview of modules and description of connection between these modules.

Base modules
============

  - :class:`hq.lib.hQBaseServer` - base class for :class:`hq.lib.hQServer`, :class:`hq.lib.hQUserServer`, :class:`hq.lib.hQExecServer`
  - :class:`hq.lib.hQCommand` - defines a command using in :class:`hq.lib.hQServer`, :class:`hq.lib.hQUserServer`, :class:`hq.lib.hQExecServer`
  - :class:`hq.lib.hQJobSchedulerSimple` - defines simple schema for job scheduling
  - :class:`hq.lib.hQLogger` - defines a logger class
  - :class:`hq.lib.hQServerDetails` - handles reading and writing of details of one of the servers :class:`hq.lib.hQServer`, :class:`hq.lib.hQUserServer`, :class:`hq.lib.hQExecServer`
  - :class:`hq.lib.hQServerProxy` - defines a proxy for one of the servers :class:`hq.lib.hQServer`, :class:`hq.lib.hQUserServer`, :class:`hq.lib.hQExecServer`
  - :class:`hq.lib.hQSocket` - defines socket connection between servers or client and server
  - :class:`hq.lib.hQUtils` - defines some utility functions and classes

Server modules
==============

  - :class:`hq.lib.hQServer` - main hq server
  - :class:`hq.lib.hQUserServer` - user's server
  - :class:`hq.lib.hQExecServer` - user's execution server

Database modules
================

  - :class:`hq.lib.hQDBSessionRegistry` - defines objects which are needed for creating a connection to the database
  - :class:`hq.lib.hQDatabase` - defines database structure
  - :class:`hq.lib.hQDBConnection` - defines a class for establishing a connection to the database
    
Modules
=======

.. toctree::
   
   hq.lib.daemon
   hq.lib.hQBaseServer
   hq.lib.hQCommand
   hq.lib.hQDatabase
   hq.lib.hQDBConnection
   hq.lib.hQDBSessionRegistry
   hq.lib.hQExecServer
   hq.lib.hQJobSchedulerSimple
   hq.lib.hQLogger
   hq.lib.hQServerDetails
   hq.lib.hQServerProxy
   hq.lib.hQServer
   hq.lib.hQSocket
   hq.lib.hQUserServerProxy
   hq.lib.hQUserServer
   hq.lib.hQUtils
