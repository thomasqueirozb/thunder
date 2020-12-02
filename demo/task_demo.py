#!/usr/bin/env python3
import datetime
import argparse
import os
import sys

import thunder
from requests_toolbelt import sessions

parser = argparse.ArgumentParser()
parser.add_argument("-r", "--region", type=str, required=True)
parser.add_argument("-p", "--project-name", type=str, required=True)
parser.add_argument("-lb", "--load-balancer", type=str)

group = parser.add_mutually_exclusive_group()
group.add_argument("--delete-all", action="store_true")
group.add_argument("-d", "--delete", type=str)
group.add_argument("--get-all", action="store_true")
group.add_argument("-g", "--get", type=str)
group.add_argument("-c", "--create", type=str)

args = parser.parse_args()
# print(args)

pname = f"{args.region}_{args.project_name}"
thunder_path = thunder.Thunder.get_data_path()
proj_path = os.path.join(thunder_path, pname)

if not os.path.isdir(proj_path):
    print(f"Directory {pname} not found in {thunder_path}")
    sys.exit(1)

lb_path = os.path.join(proj_path, "lb")
if not os.path.isdir(lb_path):
    print(f"Directory {lb_path} does not exist")
    sys.exit(1)

lbs = os.listdir(lb_path)
if len(lbs) == 0:
    print(f"No load balancers found in directory {lb_path}")
    sys.exit(1)
elif len(lbs) == 1:
    lb = lbs[0]
else:
    if args.load_balancer:
        if args.load_balancer in lbs:
            lb = lbs.index(args.load_balancer)
        else:
            print(
                f"Found multiple load balancers in directory {lb_path}",
                f"which do not match argument --load-balancer {args.load_balancer}",
            )
            sys.exit(2)

    else:
        print(
            f"Multiple load balancers found in directory {lb_path} and",
            "--load-balancer not specified",
        )
        sys.exit(1)

with open(os.path.join(lb_path, lb), "r") as f:
    url = f.read()

# print(url)
base_url = f"http://{url}:8080/"
tasks = sessions.BaseUrlSession(base_url=base_url)

req = None
if args.delete_all:
    req = tasks.delete("/tasks/delete_all")
elif args.delete:
    req = tasks.delete(f"/tasks/delete/{args.delete}")
elif args.get_all:
    req = tasks.get("/tasks/query_all")
elif args.get:
    req = tasks.get(f"/tasks/query/{args.get}")
elif args.create:
    title, description = args.create.split(",")

    req = tasks.post(
        "/tasks/new/",
        json={
            "title": title,
            "pub_date": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "description": description,
        },
    )

if req is not None:
    print(req.status_code, req.text)
