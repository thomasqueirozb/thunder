#!/usr/bin/env python3

import argparse
from thunder import Thunder

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--delete", action="store_true")

t1: Thunder = Thunder("django", "us-east-1")
t2: Thunder = Thunder("postgres", "us-east-2")

args = parser.parse_args()
if args.delete:
    t1.delete_project()
    t2.delete_project()

else:
    postgres_instance = t2.create_instance(
        "ami-0dd9f0e7df0f0a138", start_script="postgres.sh", tcp_ports=[22, 5432]
    )
    with open("django.sh", "r") as f:
        django_script_data = f.read().replace("IP_PLACEHOLDER", postgres_instance.public_ip_address)

    django_instance = t1.create_instance(
        "ami-0817d428a6fb68645", start_script_data=django_script_data, tcp_ports=[22, 8080]
    )

    ami_id = t1.create_ami(django_instance)
    t1.terminate_instance(django_instance)
    lb_name, lb_dnsname = t1.create_load_balancer()
    lc_name = t1.create_launch_config(ami_id)
    as_name = t1.create_auto_scaling(lc_name, lb_name)
