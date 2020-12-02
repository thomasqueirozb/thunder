from typing import Optional, Dict, List, Any, Iterator, Tuple
import logging
import os
import sys
import time
import string
import random

import boto3
import botocore
from botocore.exceptions import ClientError

from .version import __version__

# logging.basicConfig(level=logging.DEBUG)


# class Instance:
#     ip: str

#     def __init__(self, ip: str):
#         self.ip = ip
logger = logging.getLogger("thunder")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(name)s] [%(levelname)s] %(message)s"))
logger.addHandler(handler)


class Thunder:
    _thunder_ver_filter: Dict[str, str] = {"Name": "tag:thunder", "Values": [__version__]}
    _thunder_proj_filter: Dict[str, str]
    _thunder_ver_tag: Dict[str, str] = {"Key": "thunder", "Value": __version__}
    _thunder_proj_tag: Dict[str, str]

    tags: List[Dict[str, str]]
    filters: List[Dict[str, str]]

    ec2: boto3.resources.base.ServiceResource
    client: botocore.client.BaseClient
    project_name: str

    region: str
    _project_path: str
    _keys_path: str
    _sec_group_path: str
    _lb_path: str
    _lc_path: str
    _as_path: str
    _ami_path: str
    _pname: str

    def __init__(self, project_name: str, region: str, version_incompatible: bool = True):
        self.region = region
        self.ec2 = boto3.resource("ec2", region_name=region)
        self.client = boto3.client("ec2", region_name=region)

        self.elb_client = boto3.client("elb", region_name=region)
        self.as_client = boto3.client("autoscaling")  # , region_name=region)

        self.project_name = project_name
        self._thunder_proj_tag = {"Key": "thunder_project", "Value": project_name}
        self._thunder_proj_filter = {"Name": "tag:thunder_project", "Values": [project_name]}

        self.tags = [self._thunder_proj_tag, self._thunder_ver_tag]
        if version_incompatible:
            self.filters = [self._thunder_proj_filter, self._thunder_ver_filter]
        else:
            self.filters = [self._thunder_proj_filter]

        self._pname = f"{self.region}_{self.project_name}"
        self._create_dirs()

    def __repr__(self):
        return f"Thunder({self.region}, {self.project_name})"

    def __str__(self):
        return f"Thunder({self.region}, {self.project_name})"

    def _create_random_name(self, use_pname=True, n=8):

        if use_pname:
            return (
                self._pname
                + "_"
                + "".join(random.choice(string.ascii_letters + string.digits) for i in range(8))
            )
        return "".join(random.choice(string.ascii_letters + string.digits) for i in range(8))

    @staticmethod
    def get_data_path():
        config_path = os.getenv("XDG_CONFIG_HOME")
        if config_path is None:
            home = os.getenv("HOME", default="~")
            config_path = os.path.join(home, ".config")

        return os.path.join(config_path, "thunder")

    def _create_dirs(self):
        # Create base directory
        config_path = os.getenv("XDG_CONFIG_HOME")
        if config_path is None:
            home = os.getenv("HOME", default="~")
            config_path = os.path.join(home, ".config")

        data_path = os.path.join(config_path, "thunder")
        self._project_path = os.path.join(data_path, self._pname)
        self._keys_path = os.path.join(self._project_path, "ssh")
        self._sec_group_path = os.path.join(self._project_path, "sec_groups")
        self._ami_path = os.path.join(self._project_path, "amis")
        self._lb_path = os.path.join(self._project_path, "lb")
        self._lc_path = os.path.join(self._project_path, "lc")
        self._as_path = os.path.join(self._project_path, "as")

        def dir_create(d):
            if not os.path.isdir(d):
                os.mkdir(d)
                os.chmod(d, 0o700)

        if not os.path.isdir(data_path):
            os.mkdir(data_path)
        dir_create(self._project_path)
        dir_create(self._keys_path)
        dir_create(self._sec_group_path)
        dir_create(self._ami_path)
        dir_create(self._lb_path)
        dir_create(self._lc_path)
        dir_create(self._as_path)

    def create_instances(
        self,
        image_id: str,
        start_script_data: Optional[str] = None,
        start_script: Optional[str] = None,
        itype: str = "t2.micro",
        tcp_ports: Iterator[int] = (22,),
        udp_ports: Iterator[int] = tuple(),
        count: Iterator[int] = (1, 1),
        # key_name: Optional[str] = None
    ):
        min_count, max_count = count
        if start_script and start_script_data:
            raise RuntimeError(
                "Thunder.create_instances cannot get both start_script_data \
and start_script as arguments"
            )
        if start_script:
            with open(start_script, "r") as f:
                start_script_data = f.read()
        else:
            if not start_script_data:
                start_script_data = ""
        # print(start_script_data)

        # if key_name is None:
        #     key_name = self._pname

        self.require_key_pair()
        sg_id = self.require_security_group(tcp_ports, udp_ports)

        instances = self.ec2.create_instances(
            ImageId=image_id,
            MinCount=min_count,
            MaxCount=max_count,
            InstanceType=itype,
            SecurityGroupIds=[sg_id],
            UserData=start_script_data,
            KeyName=self._pname,  # Same key for whole project
            TagSpecifications=[{"ResourceType": "instance", "Tags": self.tags}],
        )

        for instance in instances:
            logger.info("%s - Creating instance with id %s and waiting until ok", self, instance.id)

            waiter = self.client.get_waiter("instance_status_ok")
            waiter.wait(InstanceIds=[instance.id])
            # instance.wait_until_running() # This doesnt wait for the start script
            instance.load()
            logger.info(
                "%s - Instance with id %s has public ip %s",
                self,
                instance.id,
                instance.public_ip_address,
            )

        return instances

    def create_instance(
        self,
        image_id: str,
        start_script_data: Optional[str] = None,
        start_script: Optional[str] = None,
        itype: str = "t2.micro",
        tcp_ports: Iterator[int] = (22,),
        udp_ports: Iterator[int] = tuple(),
    ):
        """Wrapper for create_instances"""
        return self.create_instances(
            image_id,
            start_script_data,
            start_script,
            itype=itype,
            count=[1, 1],
            tcp_ports=tcp_ports,
            udp_ports=udp_ports,
        )[0]

    def delete_project(self, folders=False):
        """Terminate all instances and key pairs associated with the project"""
        self.delete_all_auto_scaling()
        self.delete_all_launch_configs()
        self.delete_all_load_balancers()

        self.delete_all_amis()

        # Do terminate_all_instances before deleting keys se we still have access if error occurs
        self.terminate_all_instances()
        self.delete_all_key_pairs()

        self.delete_all_security_groups()

        if folders:
            os.rmdir(self._lb_path)
            os.rmdir(self._lc_path)
            os.rmdir(self._as_path)
            os.rmdir(self._ami_path)
            os.rmdir(self._sec_group_path)
            os.rmdir(self._keys_path)
            os.rmdir(self._project_path)

    def terminate_instance(self, instance):
        logger.info("%s - Terminating instance with id %s", self, instance.id)
        instance.terminate()

        instance.wait_until_terminated()
        logger.info("%s - Terminated instance with id %s", self, instance.id)

    def terminate_all_instances(self, instance_status: Optional[str] = None):
        """
        Terminate all instances from this project.
        Returns the terminated instances.
        """
        instances = self.filter_instances(instance_status=instance_status)

        # Send terminate to all and then wait
        for instance in instances:
            logger.info("%s - Terminating instance with id %s", self, instance.id)
            instance.terminate()

        for instance in instances:
            instance.wait_until_terminated()
            logger.info("%s - Terminated instance with id %s", self, instance.id)

        return instances

    def filter_instances(
        self,
        instance_status: Optional[str] = "running",
        custom_filters: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Any]:
        filters = self.filters.copy()
        if instance_status:
            filters.append(
                {"Name": "instance-state-name", "Values": [instance_status]},
            )
        if custom_filters:
            filters += custom_filters

        f = self.client.describe_instances(Filters=filters)
        ids = []
        for reservation in f["Reservations"]:
            for instance in reservation["Instances"]:
                ids.append(instance["InstanceId"])

        return [self.ec2.Instance(i) for i in ids]

    def require_key_pair(self):
        if len(os.listdir(self._keys_path)) == 0:
            self.create_key_pair()

    def create_key_pair(self):
        logger.info("%s - Creating key pair", self)

        response = self.client.create_key_pair(
            KeyName=self._pname,
            TagSpecifications=[{"ResourceType": "key-pair", "Tags": self.tags}],
        )

        logger.info(
            "%s - Created key pair with id %s and name %s",
            self,
            response["KeyPairId"],
            self._pname,
        )

        kpp = os.path.join(self._keys_path, response["KeyPairId"])
        with open(kpp, "w+") as f:
            f.write(response["KeyMaterial"])
        os.chmod(kpp, 0o600)

    def delete_key_pair(self, kp_id: str):
        self.client.delete_key_pair(KeyPairId=kp_id)
        logger.info("%s - Deleting key pair %s", self, kp_id)
        kp_path = os.path.join(self._keys_path, kp_id)
        if os.path.isfile(kp_path):
            os.remove(kp_path)

    def delete_all_key_pairs(self):
        for kp_id in os.listdir(self._keys_path):
            self.delete_key_pair(kp_id)

        key_ids = self.client.describe_key_pairs(Filters=self.filters)
        for key in key_ids["KeyPairs"]:
            kp_id = key["KeyPairId"]
            self.delete_key_pair(kp_id)

    def require_security_group(
        self, tcp_ports: Iterator[int] = tuple(), udp_ports: Iterator[int] = tuple()
    ) -> str:
        tcp_ports = sorted(tcp_ports)
        udp_ports = sorted(udp_ports)

        for sg in os.listdir(self._sec_group_path):
            with open(os.path.join(self._sec_group_path, sg), "r") as f:
                sg_tcp_ports, sg_udp_ports = [
                    [int(p) for p in line.split(",") if p != ""] for line in f.read().splitlines()
                ]
                if sg_tcp_ports == tcp_ports and sg_udp_ports == udp_ports:
                    return sg

        tcp_ports_str: List[str] = [str(i) for i in tcp_ports]
        udp_ports_str: List[str] = [str(i) for i in udp_ports]
        gname = f'{self._pname}_{hash("".join(tcp_ports_str) + "".join(udp_ports_str))}'
        logger.info("%s - Creating security group with name %s", self, gname)

        tcp_sec = [
            {
                "IpProtocol": "tcp",
                "FromPort": port,
                "ToPort": port,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
            for port in tcp_ports
        ]
        udp_sec = [
            {
                "IpProtocol": "udp",
                "FromPort": port,
                "ToPort": port,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
            }
            for port in udp_ports
        ]

        response = self.client.create_security_group(
            GroupName=gname,
            Description="Security group automatically generated by thunder",
            TagSpecifications=[{"ResourceType": "security-group", "Tags": self.tags}],
        )

        sg_id = response["GroupId"]

        self.client.authorize_security_group_ingress(
            GroupId=sg_id, IpPermissions=(tcp_sec + udp_sec)
        )

        logger.info(
            "%s - Created security_group with id %s",
            self,
            sg_id,
        )

        sgp = os.path.join(self._sec_group_path, sg_id)
        with open(sgp, "w+") as f:
            f.write(",".join(tcp_ports_str))
            f.write("\n")
            f.write(",".join(udp_ports_str))
            f.write("\n")
        os.chmod(sgp, 0o600)
        return sg_id

    def delete_security_group(self, sg_id: str) -> bool:
        """Deletes all security group with id sg_id
        Returns True on success, False otherwise"""
        try:
            self.client.delete_security_group(GroupId=sg_id)
            logger.info("%s - Deleted security_group %s", self, sg_id)
        except ClientError as ce:
            print(ce, file=sys.stderr)
            logger.error("%s - Failed to delete security_group %s", self, sg_id)
            return False
        sg_path = os.path.join(self._sec_group_path, sg_id)
        if os.path.isfile(sg_path):
            os.remove(sg_path)
        return True

    def delete_all_security_groups(self):
        """Deletes all security_groups from the project"""
        for sg_id in os.listdir(self._sec_group_path):
            self.delete_security_group(sg_id)

        for sg in self.client.describe_security_groups(Filters=self.filters)["SecurityGroups"]:
            sg_id = sg["GroupId"]
            self.delete_security_group(sg_id)

    def create_ami(self, instance) -> str:
        ami_name = self._create_random_name()

        iid = instance.id
        logger.info("%s - Creating AMI with name %s from instance %s", self, ami_name, iid)
        # There seems to have no way to tag an ami
        response = self.client.create_image(InstanceId=iid, Name=ami_name, NoReboot=True)
        ami_id = response["ImageId"]
        logger.debug(
            "%s - Waiting for AMI with name %s and id %s to be created from instance %s",
            self,
            ami_name,
            ami_id,
            iid,
        )
        waiter = self.client.get_waiter("image_available")
        waiter.wait(ImageIds=[ami_id])
        logger.info(
            "%s - Created AMI with name %s and id %s from instance %s",
            self,
            ami_name,
            ami_id,
            iid,
        )

        with open(os.path.join(self._ami_path, ami_id), "w+") as f:
            f.write(ami_name)

        return ami_id

    def delete_ami(self, ami_id: str):
        self.client.deregister_image(ImageId=ami_id)
        logging.info("%s - Deleted AMI with id %s", self, ami_id)
        ami_path = os.path.join(self._ami_path, ami_id)
        if os.path.isfile(ami_path):
            os.remove(ami_path)

    def delete_all_amis(self):
        for ami_id in os.listdir(self._ami_path):
            self.delete_ami(ami_id)

    def create_load_balancer(
        self,
        tcp_ports: Iterator[int] = (8080,),
        udp_ports: Iterator[int] = tuple(),
    ) -> Tuple[str]:
        sg_id = self.require_security_group(tcp_ports, udp_ports)

        # tcp_ports_str: List[str] = [str(i) for i in tcp_ports]
        # udp_ports_str: List[str] = [str(i) for i in udp_ports]
        lb_name = f'thunder-lb-{"".join(random.choice(string.ascii_letters) for i in range(8))}'

        logger.info("%s - Creating load balancer with name %s", self, lb_name)

        # # elbv2 introduces lots of complications
        # response = self.elb_client.create_load_balancer(
        #     Name=lb_name,
        #     SecurityGroups=[sg_id],
        #     Tags=self.tags,
        # )

        # response = client.create_listener(
        # DefaultActions=[
        #     {
        #         'TargetGroupArn':lb_arn,
        #         'Type': 'forward',
        #     },
        # ],
        # LoadBalancerArn=lb_arn,
        # Port=80,
        # Protocol='HTTP',
        response = self.elb_client.create_load_balancer(
            LoadBalancerName=lb_name,
            Listeners=[
                {
                    "InstanceProtocol": "HTTP",
                    "InstancePort": 8080,
                    "Protocol": "HTTP",
                    "LoadBalancerPort": 8080,
                }
            ],
            Subnets=[s["SubnetId"] for s in self.client.describe_subnets()["Subnets"]],
            SecurityGroups=[sg_id],
            Tags=self.tags,  # There is no reference to Filter in elb docs, only describe_tags
        )
        lb_dnsname = response["DNSName"]

        logger.info(
            "%s - Waiting for load balancer with name %s and DNS %s to be created",
            self,
            lb_name,
            lb_dnsname,
        )
        with open(os.path.join(self._lb_path, lb_name), "w+") as f:
            f.write(lb_dnsname)

        while True:
            response = self.elb_client.describe_load_balancers()
            for lb in response["LoadBalancerDescriptions"]:
                if lb["LoadBalancerName"] == lb_name:
                    return lb_name, lb_dnsname
            # The elbv2 waiter calls describe_load_balancers after 15 seconds
            time.sleep(15)

    def delete_all_load_balancers(self):
        # TODO this doesnt use tags so no external checks (.describe_...()) are done
        lb_names = os.listdir(self._lb_path)
        for lb_name in lb_names:
            self.elb_client.delete_load_balancer(LoadBalancerName=lb_name)
            logger.info("%s - Deleting load balancer %s", self, lb_name)
            os.remove(os.path.join(self._lb_path, lb_name))

        time.sleep(1)
        while True:
            response = self.elb_client.describe_load_balancers()
            all_lb_names = [lb["LoadBalancerName"] for lb in response["LoadBalancerDescriptions"]]
            c = True
            for lb_name in lb_names:
                if lb_name in all_lb_names:
                    c = False
            if c:
                break

            # The elbv2 waiter calls describe_load_balancers after 15 seconds
            time.sleep(15)

    def delete_all_auto_scaling(self):
        # TODO this doesnt use tags so no external checks (.describe_...()) are done
        as_names = os.listdir(self._as_path)
        for as_name in as_names:
            self.as_client.delete_auto_scaling_group(AutoScalingGroupName=as_name, ForceDelete=True)
            logger.info("%s - Deleting auto scaling %s", self, as_name)
            os.remove(os.path.join(self._as_path, as_name))
        while (
            len(
                self.as_client.describe_auto_scaling_groups(AutoScalingGroupNames=as_names)[
                    "AutoScalingGroups"
                ]
            )
            != 0
        ):

            time.sleep(1)

    def create_auto_scaling(
        self,
        lc_name: str,
        lb_name: Optional[str] = None,
        min_size: int = 2,
        max_size: int = 10,
        desired: int = 2,
    ) -> str:
        as_name = self._create_random_name()

        logger.info("%s - Creating auto scaling %s", self, as_name)

        self.as_client.create_auto_scaling_group(
            AutoScalingGroupName=as_name,
            LaunchConfigurationName=lc_name,
            MinSize=min_size,
            MaxSize=max_size,
            LoadBalancerNames=[] if lb_name is None else [lb_name],
            AvailabilityZones=[
                z["ZoneName"]
                for z in self.client.describe_availability_zones()["AvailabilityZones"]
            ],
            Tags=self.tags,  # not checked
        )

        while (
            len(
                self.as_client.describe_auto_scaling_groups(AutoScalingGroupNames=[as_name])[
                    "AutoScalingGroups"
                ]
            )
            == 0
        ):
            time.sleep(1)

        logger.info("%s - Created auto scaling %s", self, as_name)
        open(os.path.join(self._as_path, as_name), "w+").close()

        return as_name

    def create_launch_config(
        self,
        ami_id: str,
        tcp_ports: Iterator[int] = (8080,),
        udp_ports: Iterator[int] = tuple(),
        itype: str = "t2.micro",
        monitoring: bool = False,
    ) -> str:

        sg_id = self.require_security_group(tcp_ports, udp_ports)
        lc_name = self._create_random_name()
        self.require_key_pair()
        key_name = self._pname  # Same key for whole project

        logger.info(
            "%s - Creating launch configuration %s with type %s and monitoring %s",
            self,
            lc_name,
            itype,
            "enabled" if monitoring else "disabled",
        )

        # Taggind doesnt have an effect
        self.as_client.create_launch_configuration(
            LaunchConfigurationName=lc_name,
            ImageId=ami_id,
            KeyName=key_name,
            SecurityGroups=[sg_id],
            InstanceType=itype,
            InstanceMonitoring={"Enabled": monitoring},
        )

        while (
            len(
                self.as_client.describe_launch_configurations(LaunchConfigurationNames=[lc_name])[
                    "LaunchConfigurations"
                ]
            )
            == 0
        ):
            time.sleep(1)

        logger.info(
            "%s - Created launch configuration %s with type %s and monitoring %s",
            self,
            lc_name,
            itype,
            "enabled" if monitoring else "disabled",
        )

        with open(os.path.join(self._lc_path, lc_name), "w+") as f:
            f.write(ami_id)
            f.write("\n")
            f.write(key_name)
            f.write("\n")
            f.write(sg_id)
            f.write("\n")
            f.write(itype)
            f.write("\n")

        return lc_name

    def _delete_launch_configs(self, lc_names: List[str]):
        for lc_name in lc_names:
            self.as_client.delete_launch_configuration(LaunchConfigurationName=lc_name)
            logger.info("%s - Deleting launch config %s", self, lc_name)

            lc_path = os.path.join(self._lc_path, lc_name)
            if os.path.isfile(lc_path):
                os.remove(lc_path)

        time.sleep(1)

        while (
            len(
                self.as_client.describe_launch_configurations(LaunchConfigurationNames=lc_names)[
                    "LaunchConfigurations"
                ]
            )
            != 0
        ):
            time.sleep(1)

    def delete_launch_config(self, lc_name: str):
        self._delete_launch_configs([lc_name])

    def delete_all_launch_configs(self):
        # TODO this doesnt use tags so no external checks (.describe_...()) are done

        lc_names = os.listdir(self._lc_path)
        if len(lc_names) == 0:
            return
        self._delete_launch_configs(lc_names)
