"""defines a scoped session for creating thread local session by calling self.DBSession

See: :url:`http://docs.sqlalchemy.org/en/latest/orm/session_basics.html#what-does-the-session-do`
for more info about sessions.

See: :url:`http://docs.sqlalchemy.org/en/rel_0_9/orm/session.html#contextual-thread-local-sessions`
for thread local sessions which have to be using in web environments or other multithread
applications.

A session factory and a scoped session is created

**SessionFactory**::
 
  see: :url:`http://docs.sqlalchemy.org/en/rel_0_9/orm/session.html`
  
  Session is a regular Python class which can be directly instantiated. However, to standardize how
  sessions are configured and acquired, the sessionmaker class is normally used to create a top
  level Session configuration which can then be used throughout an application without the need to
  repeat the configurational arguments.  sessionmaker() is a Session factory. A factory is just
  something that produces a new object when called.

**DBSession**::

  see 'url':`http://docs.sqlalchemy.org/en/rel_0_9/orm/session.html#contextual-thread-local-sessions` for
  thread local sessions which have to be using in web environments or other multithread applications.
  
  DBSession is a scoped Session class which will serve as a factory for new Session objects
  
  A scoped session is constructed by calling :func:`sqlalchemy.orm.scoped_session`, passing it a
  factory which can create new Session objects. A factory is just something that produces a new
  object when called, and in the case of Session
  
  If we call upon the registry DBSession a second time, we get back the same Session.

"""

import os
import sys
import ConfigParser
import sqlalchemy.orm


# import hq libraries
from hq.lib.hQDatabase import Base

# use default config file
ETCPATH = "{etcpath}/etc".format( etcpath=os.environ['HQPATH'] )

# default config file for database connection
configFileName = "{etcPath}/hq-db.cfg".format(etcPath=ETCPATH)

# read config file
if os.path.exists( configFileName ):
    config = ConfigParser.ConfigParser()
    config.read( configFileName )
else:
    sys.stderr.write( "ERROR: Could not find Config file {c}!".format( c=configFileName) )
    sys.exit( -1 )

databaseDialect = config.get( 'DATABASE', 'database_dialect' )
databaseHost = config.get( 'DATABASE', 'database_host' )
databasePort = config.get( 'DATABASE', 'database_port' )
databaseName = config.get( 'DATABASE', 'database_name' )
databaseUsername = config.get( 'DATABASE', 'database_username' )
databasePassword = config.get( 'DATABASE', 'database_password' )

try:
    echo = config.getboolean( 'DATABASE', 'echo' )
except:
    echo = False
 

def get_engine( echo=False ):
    """get a database engine

    **Kwargs**
      echo (bool): if True print SQL printing statements to stdout

    **Returns**
      database engine

    .. note::

       connection details are stored in outer score
       
    """
    
    engine = sqlalchemy.create_engine( "{dialect}://{user}:{password}@{host}:{port}/{name}".format( dialect=databaseDialect,
                                                                                                    user=databaseUsername,
                                                                                                    password=databasePassword,
                                                                                                    host=databaseHost,
                                                                                                    port=databasePort,
                                                                                                    name=databaseName), 
                                       pool_size=10, # number of connections to keep open inside the connection pool
                                       max_overflow=100, # number of connections to allow in connection pool "overflow", that is connections that can be opened above and beyond the pool_size setting, which defaults to five.
                                       pool_recycle=3600, # this setting causes the pool to recycle connections after the given number of seconds has passed. 
                                       echo=echo )
    return engine

## engine
engine = get_engine( echo=echo )

## define a session factory
SessionFactory = sqlalchemy.orm.sessionmaker( bind = engine )

## define a scoped session which will serve as a factory for new Session objects
DBSession = sqlalchemy.orm.scoped_session( SessionFactory )


def init_db( e=None ):
    """! @brief Create all tables in the engine.

    @param e database engine
    
    This is equivalent to 'CREATE TABLE' statements in raw SQL.
    """
    
    Base.metadata.create_all( bind=e if e else engine )


