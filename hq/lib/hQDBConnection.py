import os
import sys

from sqlalchemy import MetaData
#from sqlalchemy.orm import sessionmaker, scoped_session

# import hq libraries
import hq.lib.hQDBSessionRegistry as hQDBSessionRegistry

DBSession = hQDBSessionRegistry.DBSession
engine = hQDBSessionRegistry.engine


class hQDBConnection( object ):
    """database connection

    A session is creating by calling :obj:`DBSession` which is defined in
    :class:`hq.lib.hQDBSessionRegistry`. A DBSession instance establishes all conversations with the
    database and represents a 'staging zone' for all the objects loaded into the database session
    object. Any change made against the objects in the session won't be persisted into the database
    until you call session.commit(). If you're not happy about the changes, you can revert all of
    them back to the last commit by calling session.rollback()
    """
    
    def __init__( self, echo=False ):
        # create a connection to the database
        self.session = DBSession()
        
    #def __del__( self ):
    #    """! @brief Tidy up session upon destruction of the Connect object"""
    #    self.session.remove()

    def query( self, *args, **kwargs ):
        """alias for session.query()

        **Args**
          args: Arguments that should be forwarded to session.query
          
        **Kwargs**
          kwargs: Keyword arguments that should be forwarded to session.query
        
        **Returns**
          A query object that can be further refined
          
        """
        
        return self.session.query( *args, **kwargs )


    def introduce( self, *objects ):
        """Prepare objects for commit to the database by adding to session

        :func:`session.add()` is called for each object.

        Pending transactions are execute after calling :meth:`commit`.
        
        **Args**
          objects: Any number of database objects that should be introduced to the database

        **Return**
          self
          
        """
        for obj in objects:
            self.session.add( obj )

        return self
 
    def delete( self, *objects ):
        """Mark objects for deletion from the database.

        :func:`session.delete()` is called for each object
        
        Pending transactions are execute after calling :meth:`commit`.
        
        **Args**
          objects Any number of database objects that should be deleted.

        **Return**
          self
        """
        
        for obj in objects:
            self.session.delete( obj )
            
        return self

    def commit( self ):
        """Commit all objects that have been prepared

        **Return**
          value from sqlalchemy's :func:`session.commit()`
        """
        return self.session.commit()

    def remove( self ):
        """tell registry to dispose session
        """
        
        DBSession.remove()
        
    def create_all_tables( self ):
        """create tables defined in database model in database if not exist

        """
        
        from hDatabase import Base
        
        Base.metadata.create_all( engine )

    def drop_all_tables( self ):
        """drop all tables in database

        .. warning:: This will really drop all tables including their contents.
        """


        meta = MetaData( engine )
        meta.reflect()
        meta.drop_all()

