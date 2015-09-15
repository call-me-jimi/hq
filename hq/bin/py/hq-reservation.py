#!/usr/bin/env python
#
# hq/bin/py/hq-reservation - manage slot reservations
#

PROGNAME = "hq-reservation"

import sys
import os
import argparse
import textwrap
import sqlalchemy
import ConfigParser
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import func
from sqlalchemy import and_, or_, not_, func
from datetime import datetime
import traceback
import random

# for debugging
from pprint import pprint as pp


# logging
import logging
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.ERROR)			# logger level. can be changed with command line option -v

formatter = logging.Formatter('[%(asctime)-15s] %(message)s')

# create console handler and configure
consoleLog = logging.StreamHandler(sys.stdout)
consoleLog.setLevel(logging.INFO)		# handler level. 
consoleLog.setFormatter(formatter)

# add handler to logger
logger.addHandler(consoleLog)

# import hq libraries
from hq.lib.hQDBConnection import hQDBConnection
import hq.lib.hQDatabase as db


class ValidateVerboseMode(argparse.Action):
    def __call__(self, parser, namespace, value, option_string=None):
        #print '{n} -- {v} -- {o}'.format(n=namespace, v=value, o=option_string)

        # set level of logger to INFO
        logger.setLevel( logging.INFO )
        
        # set attribute self.dest
        setattr(namespace, self.dest, True)


def print_reservation( reservation, con ):
    numSlots, = con.query( func.sum( db.ReservedSlots.slots) ).filter( db.ReservedSlots.reservation==reservation ).one()
    print "{t:>20} : {v}".format( t='regisration code', v=reservation.code )
    print "{t:>20} : {v}".format( t='created at', v=reservation.datetime )
    print "{t:>20} : {v}".format( t='total number slots', v=numSlots )
    for idx,resevedSlot in enumerate(reservation.reserved_slots):
        if idx==0:
            print "{t:>20} : {host} - {slot}".format( t='hosts / slots', host=resevedSlot.host.full_name, slot=resevedSlot.slots )
        else:
            print "{t:>20}   {host} - {slot}".format( t='', host=resevedSlot.host.full_name, slot=resevedSlot.slots )
    print
    
if __name__ == '__main__':
    textWidth = 80
    parser = argparse.ArgumentParser(
        prog=PROGNAME,
        usage="%(prog)s [-h --help] [options]",
        description="Manage reservations of slots in cluster.",
        epilog='Written by Hendrik.' )

    parser.add_argument('-a', '--add-reservation',
                        dest = 'addReservation',
                        action = 'store_true',
                        default = False,
                        help = 'Add a reservation.'
                        )
    
    parser.add_argument('-d', '--delete-reservation',
                        metavar = 'CODE',
                        dest = 'deleteReservation',
                        default = "",
                        help = 'Delete the reservation with the given code.'
                        )
    
    parser.add_argument('-s', '--show-reservations',
                        dest = 'showReservations',
                        action = 'store_true',
                        default = False,
                        help = 'Show active reservations.'
                        )
    
    parser.add_argument('-v', '--verbose-mode',
                        nargs = 0,
                        dest = 'verboseMode',
                        action = ValidateVerboseMode,
                        default = False,
                        help = 'Activate verbose mode.'
                        )
    
    args = parser.parse_args()

    logger.info( "Welcome to {p}!".format(p=PROGNAME) )

    if args.showReservations:
        con = hQDBConnection()

        reservations = con.query( db.Reservation ).all()

        for reservation in reservations:
            print_reservation( reservation, con )

        if not reservations:
            print "there are no reservations."
                    
    elif args.addReservation:
        #questions = [ { 'question': 'Number of slots? ',
        #                'answer': "" } ]
        #
        #for q in questions:
        #    q['answer']  = raw_input( q['question'] )

        con = hQDBConnection()
        
        reservation_codes = set(con.query( db.Reservation.code ).all())
        
        while True:
            new_reservation_code = hex(random.getrandbits(32))[2:-1].upper()
            if new_reservation_code not in reservation_codes:
                break

        new_reservation = db.Reservation( code = new_reservation_code )
        con.introduce(new_reservation)
        
        
        hosts = con.query( db.Host )\
                .join( db.HostSummary )\
                .filter( and_(db.HostSummary.available==True,
                              db.HostSummary.reachable==True,
                              db.HostSummary.active==True
                              ) )

        reserve_slots = {}
        print "Specify for each host the number of slots which will be reserved (default 0)"
        for host in hosts:
            reserve_slots[ host.id ] = raw_input( "  {h} [max: {m}]: ".format(h=host.full_name,m=host.max_number_occupied_slots ) )
            try:
                reserve_slots[ host.id ] = int( reserve_slots[ host.id ] )
                if reserve_slots[ host.id ] > host.max_number_occupied_slots:
                    reserve_slots[ host.id ] = host.max_number_occupied_slots

                if reserve_slots[ host.id ]>0:
                    new_reserved_slots = db.ReservedSlots( reservation=new_reservation,
                                                           slots = reserve_slots[ host.id ],
                                                           host = host )
                    con.introduce( new_reserved_slots )
                    
            except:
                reserve_slots[ host.id ] = 0

        
        con.commit()

        print
        print "A reservation has been added:"
        print_reservation( new_reservation, con )
        
   

    elif args.deleteReservation:
        # how to do it more effciently?
        con = hQDBConnection()

        reservations = con.query( db.Reservation ).filter( db.Reservation.code==args.deleteReservation )

        # delete ReservedSlots
        for reservation in reservations:
            d = con.query( db.ReservedSlots )\
                .filter( db.ReservedSlots.reservation==reservation )\
                .delete()
        # delete Reservation
        d = con.query( db.Reservation ).filter( db.Reservation.code==args.deleteReservation ).delete()

        con.commit()
        
        print "done"


    logger.info( "Thank you for using {p}!".format( p=PROGNAME ) )



