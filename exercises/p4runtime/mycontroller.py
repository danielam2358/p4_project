#!/usr/bin/env python2
import argparse
import os
import sys
from time import sleep

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
import p4runtime_lib.helper

SWITCH_TO_HOST_PORT = 1
SWITCH_TO_SWITCH_PORT = 2
S1_TO_S2_PORT = 2
S1_TO_S3_PORT = 3
S2_TO_S1_PORT = 2
S2_TO_S3_PORT = 3
S3_TO_S1_PORT = 2
S3_TO_S2_PORT = 3
MIRROR_PORT = 3

switcher = {
    102: S1_TO_S2_PORT,
    103: S1_TO_S3_PORT,
    201: S2_TO_S1_PORT,
    203: S2_TO_S3_PORT,
    301: S3_TO_S1_PORT,
    302: S3_TO_S2_PORT,
    113: S1_TO_S3_PORT  # tunnel_id for s1 to s3 mirroring.
}


def write_tunnel_rules(p4info_helper, ingress_sw, egress_sw, tunnel_id, dst_eth_addr, dst_ip_addr):
    """
    Installs three rules:
    1) An tunnel ingress rule on the ingress switch in the ipv4_lpm table that
       encapsulates traffic into a tunnel with the specified ID
    2) A transit rule on the ingress switch that forwards traffic based on
       the specified ID
    3) An tunnel egress rule on the egress switch that decapsulates traffic
       with the specified ID and sends it to the host

    :param p4info_helper: the P4Info helper
    :param ingress_sw: the ingress switch connection
    :param egress_sw: the egress switch connection
    :param tunnel_id: the specified tunnel ID
    :param dst_eth_addr: the destination IP to match in the ingress rule
    :param dst_ip_addr: the destination Ethernet address to write in the
                        egress rule
    """
    # 1) Tunnel Ingress Rule
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": (dst_ip_addr, 32)
        },
        action_name="MyIngress.myTunnel_ingress",
        action_params={
            "dst_id": tunnel_id,
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed ingress tunnel rule on %s" % ingress_sw.name)

    # 2) Tunnel Transit Rule
    # The rule will need to be added to the myTunnel_exact table and match on
    # the tunnel ID (hdr.myTunnel.dst_id). Traffic will need to be forwarded
    # using the myTunnel_forward action on the port connected to the next switch.
    #
    # For our simple topology, switch 1 and switch 2 are connected using a
    # link attached to port 2 on both switches. We have defined a variable at
    # the top of the file, SWITCH_TO_SWITCH_PORT, that you can use as the output
    # port for this action.
    #
    # We will only need a transit rule on the ingress switch because we are
    # using a simple topology. In general, you'll need on transit rule for
    # each switch in the path (except the last switch, which has the egress rule),
    # and you will need to select the port dynamically for each switch based on
    # your topology.

    switch_to_switch_port = switcher.get(tunnel_id)	
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_forward",
        action_params={
            "port": switch_to_switch_port
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed transit tunnel rule on %s" % ingress_sw.name)

    # 3) Tunnel Egress Rule
    # For our simple topology, the host will always be located on the
    # SWITCH_TO_HOST_PORT (port 1).
    # In general, you will need to keep track of which port the host is
    # connected to.
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_egress",
        action_params={
            "dstAddr": dst_eth_addr,
            "port": SWITCH_TO_HOST_PORT
        })
    egress_sw.WriteTableEntry(table_entry)
    print("Installed egress tunnel rule on %s" % egress_sw.name)


def write_mirror_rules(p4info_helper, ingress_sw, egress_sw, egress_spec, tunnel_id, dst_eth_addr, session_id):
    # Mirror Rule.
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.mirror",
        match_fields={
            "standard_metadata.egress_spec": egress_spec
        },
        action_name="MyIngress.packet_clone",
        action_params={
            "session_id": session_id,
            "dst_id": tunnel_id
        })
    ingress_sw.WriteTableEntry(table_entry)
    print("Installed tunnel mirror rule on %s" % ingress_sw.name)

    # Mirror Egress Rule.
    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.myTunnel_exact",
        match_fields={
            "hdr.myTunnel.dst_id": tunnel_id
        },
        action_name="MyIngress.myTunnel_egress",
        action_params={
            "dstAddr": dst_eth_addr,
            "port": SWITCH_TO_HOST_PORT
        })
    egress_sw.WriteTableEntry(table_entry)
    print("Installed egress tunnel mirror rule on %s" % egress_sw.name)


def main(p4info_file_path, bmv2_file_path):
    # Instantiate a P4 Runtime helper from the p4info file
    p4info_helper = p4runtime_lib.helper.P4InfoHelper(p4info_file_path)

    # Create a switch connection object for s1 and s2;
    # this is backed by a P4 Runtime gRPC connection.
    # Also, dump all P4Runtime messages sent to switch to given txt files.
    s1 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
        name='s1',
        address='127.0.0.1:50051',
        device_id=0,
        proto_dump_file='logs/s1-p4runtime-requests.txt')
    s2 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
        name='s2',
        address='127.0.0.1:50052',
        device_id=1,
        proto_dump_file='logs/s2-p4runtime-requests.txt')

    s3 = p4runtime_lib.bmv2.Bmv2SwitchConnection(
        name='s3',
        address='127.0.0.1:50053',
        device_id=2,
        proto_dump_file='logs/s3-p4runtime-requests.txt')

    # Send master arbitration update message to establish this controller as
    # master (required by P4Runtime before performing any other write operation)
    s1.MasterArbitrationUpdate()
    s2.MasterArbitrationUpdate()
    s3.MasterArbitrationUpdate()

    # Install the P4 program on the switches
    s1.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                   bmv2_json_file_path=bmv2_file_path)
    print("Installed P4 Program using SetForwardingPipelineConfig on s1")
    s2.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                   bmv2_json_file_path=bmv2_file_path)
    print("Installed P4 Program using SetForwardingPipelineConfig on s2")
    s3.SetForwardingPipelineConfig(p4info=p4info_helper.p4info,
                                   bmv2_json_file_path=bmv2_file_path)
    print("Installed P4 Program using SetForwardingPipelineConfig on s3")

    # Write the rules that tunnel traffic from h1 to h2
    write_tunnel_rules(p4info_helper, ingress_sw=s1, egress_sw=s2, tunnel_id=102,
                     dst_eth_addr="00:00:00:00:02:02", dst_ip_addr="10.0.2.2")

    # Write the rules that tunnel traffic from h2 to h1
    write_tunnel_rules(p4info_helper, ingress_sw=s2, egress_sw=s1, tunnel_id=201,
                     dst_eth_addr="00:00:00:00:01:01", dst_ip_addr="10.0.1.1")

    # Write the rules that tunnel traffic from h1 to h3
    write_tunnel_rules(p4info_helper, ingress_sw=s1, egress_sw=s3, tunnel_id=103,
                     dst_eth_addr="00:00:00:00:03:03", dst_ip_addr="10.0.3.3")
    # Write the rules that tunnel traffic from h3 to h1
    write_tunnel_rules(p4info_helper, ingress_sw=s3, egress_sw=s1, tunnel_id=301,
                     dst_eth_addr="00:00:00:00:01:01", dst_ip_addr="10.0.1.1")
    # Write the rules that tunnel traffic from h2 to h3
    write_tunnel_rules(p4info_helper, ingress_sw=s2, egress_sw=s3, tunnel_id=203,
                     dst_eth_addr="00:00:00:00:03:03", dst_ip_addr="10.0.3.3")
    # Write the rules that tunnel traffic from h3 to h2
    write_tunnel_rules(p4info_helper, ingress_sw=s3, egress_sw=s2, tunnel_id=302,
                     dst_eth_addr="00:00:00:00:02:02", dst_ip_addr="10.0.2.2")

    # ===================================#

    write_mirror_rules(p4info_helper, ingress_sw=s1, egress_sw=s3, egress_spec=3, tunnel_id=113,
                       dst_eth_addr="00:00:00:00:03:03", session_id=1)

    # ===================================#

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.p4info')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/advanced_tunnel.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)

    main(args.p4info, args.bmv2_json)
