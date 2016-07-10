
'''
    Application to manage to topology of VLANs within Faucet.
'''

import json
import os, signal, logging

from logging.handlers import TimedRotatingFileHandler

from valve import valve_factory
from util import kill_on_exception
from dp import DP

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller import dpset
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.controller import event
from ryu.ofproto import ofproto_v1_3, ether
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import vlan
from ryu.lib import hub

from ryu.lib import dpid as dpid_lib
from ryu.topology.api import get_switch, get_link


class TopologyApp(app_manager.RyuApp):

    def __init__(self, *args, **kwargs):
        super(TopologyApp, self).__init__(*args, **kwargs)

        # External filepaths.
        self.config_file = os.getenv(
            'FAUCET_CONFIG', '/etc/ryu/faucet/faucet.yaml')
        self.logfile = os.getenv(
            'FAUCET_LOG', '/var/log/ryu/faucet/faucet.log')
        self.exc_logfile = os.getenv(
            'FAUCET_EXCEPTION_LOG', '/var/log/ryu/faucet/faucet_exception.log')        

        self.log_name = 'faucet'

        # Faucet datapaths.
        self.dps = self.parse_config()

        # VLAN IDs.
        self.vids = set()

        for dp in self.dps:
            for vlan in dp.vlans:
                self.vids.add(vlan)

        self.monitor_thread = hub.spawn(self._monitor)


    def _monitor(self):
        while True:
            for vid in self.vids:
                print "VID %d: %s" % (vid, self.get_links(vid))

            hub.sleep(5)


    ##############


    def parse_config(self):
        new_dps = []
        for new_dp in DP.parser(self.config_file, self.log_name):
            try:
                new_dp.sanity_check()
                new_dps.append(new_dp)
            except AssertionError:
                pass#self.logger.exception("Error in config file:")
        return new_dps


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def handler_features(self, ev):
        msg = ev.msg
        dp = msg.datapath
        #if dp.id not in self.valves:
        #    self.logger.info("unknown dp")
        #    return
        #flowmods = self.valves[dp.id].switch_features(dp.id, msg)
        #self.send_flow_msgs(dp, flowmods)


    ##############


    def _get_physical_links(self):
        dpid = None  # want all dpids
        links = get_link(self, dpid)
        link_dict_list = [link.to_dict() for link in links]
        return link_dict_list


    @staticmethod
    def _port_no_in_vid(dp, port_no, vid):
        """
        Return true if the port number on the given dp has a given vid
        associated with it, tagged or untagged.
        """

        for p in dp.vlans[vid].untagged:
            if p.number == port_no:
                return True

        for p in dp.vlans[vid].tagged:
            if p.number == port_no:
                return True

        return False


    def get_links(self, vid):
        """
        Filter the topology links by VLAN ID, and return a set of links which are only
        associated with that ID.
        """

        vlan_links = []
        links = self._get_physical_links()

        for link in links:
            src_dp = None
            dst_dp = None

            # Find the Faucet dps for the source and destination
            # switches.
            for dp in self.dps:
                if dp.id == int(link['src']['dpid'], 16):
                    src_dp = dp
                elif dp.id == int(link['dst']['dpid'], 16):
                    dst_dp = dp

                if src_dp is not None and dst_dp is not None:
                    break

            # Add this link to vlan_links if the associated ports
            # on both dps use the given vid.
            if TopologyApp._port_no_in_vid(src_dp, int(link['src']['port_no']), vid) and TopologyApp._port_no_in_vid(dst_dp, int(link['dst']['port_no']), vid):
                vlan_links.append(link)

        return vlan_links

