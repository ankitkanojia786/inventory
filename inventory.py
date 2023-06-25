import boto3
import os
import datetime
import csv

def lambda_handler(events, context):

    #get all ec2 instances
    instances = get_all_ec2_instances()

    #define variables for the headings
    IDENTIFIER = "Identifier"
    SERVICE =  "Service"
    INSTANCE_ID = "Instance ID"
    REGION = "Region"
    INSTANCE_TYPE = "Instance Type"
    LAUNCH_TIME = "Launch Time"
    CREATION_TIME = "Cretion Time"
    DELETION_TIME = "Deletion Time"
    PRIVATE_IP = "Private IP Address"
    PUBLIC_IP = "Public IP Address"
    OS_VERSION = "OS Version"
    IAM_ROLE = "IAM Role"
    DISK_USAGE = "Disk Usage (GiB)"
    CPU = "CPU"
    RAM = "RAM (GiB)"
    TAGS = "Tags"
    # Initialize an empty array to store all instance details
    instances_details = []

    # Iterate over each instance
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            # Get the tags for the instance
            tags = instance.get('Tags',[])

            # Check if the instance has the required tags
            if 'Project' not in [tag['Key'] for tag in tags] or 'Environment' not in [tag['Key'] for tag in tags]:
                continue

            # Get the tags dictionary for the instance
            tag_dict = {tag['Key']: tag['Value'] for tag in tags}

            # Get the instance metadata
            instance_dict = {}
            instance_dict[IDENTIFIER] = f"{tags_dict['Project']} - {tags_dict['Environment']}"
            instance_dict[SERVICE] = "EC2"
            instance_dict[INSTANCE_ID] = instance['InstanceId']
            instance_dict[REGION] = instance['Placement']['AvailabilityZone'][:-1]
            instance_dict[INSTANCE_TYPE] = instance['InstanceType']
            instance_dict[LAUNCH_TIME] = str(instance['LaunchTime'].strftime('%d-%m-%y'))
            instance_dict[CREATION_TIME] = str(instance['CreateTime'].strftime('%d-%m-%y %H:%M:%S')) if 'CreateTime' in instance else 'NA'
            instance_dict[DELETION_TIME] = str(instance['StateTransitionReason']).split()[-3] if 'StateTransitionReason' in instance and 'deleting' in instance['StateTransitionReason'] else 'NA'
            instance_dict[PRIVATE_IP] = instance.get('PrivateIpAddress', '')
            instance_dict[PUBLIC_IP] = instance.get('PublicIpAddress', '')
            instance_dict[OS_VERSION] = instance['Platform'] if 'Platform' in instance else instance['ImageId']
            instance_dict[IAM_ROLE] = instance['IamInstanceProfile']['Arn'].split('/')[1] if 'IamInstanceProfile' in instance else 'NA'
            instance_dict[DISK_USAGE] = get_disk_usage(instance['InstanceId'])
            instance_dict[CPU] = get_cpu_utilization(instance['InstanceId'])
            instance_dict[RAM] = get_ram_utilization(instance['InstanceId'])
            instance_dict[TAGS] = {tag['Key']: tag['Value'] for tag in tags}

            # Write the instance details to a CSV file
            IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        filename = f"/tmp/EC2-Inventory-{datetime.datetime.now(IST).strftime('%d-%m-%Y-%H-%M-%S')}.csv"
        with open(filename, 'w') as csv_file:
            fieldnames = [IDENTIFIER, SERVICE, INSTANCE_ID, REGION, INSTANCE_TYPE, LAUNCH_TIME, CREATION_TIME, DELETION_TIME, PRIVATE_IP, PUBLIC_IP, OS_VERSION, IAM_ROLE, DISK_USAGE, CPU, RAM, TAGS]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for instance in instance_details:
                writer.writerow(instance)


        # Upload the CSV file to S3
        s3 = boto3.client('s3')
    os.environ.setdefault('S3_BUCKET','myinventory')
    s3.upload_file(filename, os.environ['S3_BUCKET'], filename)

    return {
        'statusCode': 200,
        'body': f'EC2 Inventory file "{filename}" successfully generated and uploaded to S3 bucket "{os.environ["S3_BUCKET"]}"'
    }

def get_all_ec2_instances():
    #Returns a dictionary containing all EC2 instances in the current region.
    ec2 = boto3.client('ec2')
    return ec2.describe_instances() #get all the metadata for all instances in the account.


def get_disk_usage(instance_id):
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(instance_id)
    total_size = 0
    for volume in instance.volumes.all():
        total_size += volume.size
    return total_size

#defining functions to make additional calls to Cloudwatch for ram and cpu usage
def get_cpu_utilization(instance_id):
    cloudwatch = boto3.client('cloudwatch')
    end_time = datetime.datetime.utcnow() #getting the current UTC time as a datetime object, which will be used as the end time for the metric query.
    start_time = end_time - datetime.timedelta(minutes=5) #subtracting 5 minutes from the current UTC time to get a 5-minute window of time to query metrics for. The resulting datetime object is used as the start time for the metric query.
    response = cloudwatch.get_metric_statistics(  #CloudWatch client to query the average CPU utilization for the specified instance_id
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',  #query is limited to the EC2 namespace and the CPUUtilization metric. 
        Dimensions=[                  #Dimensions parameter is used to specify the InstanceId to query for. 
            {
                'Name': 'InstanceId',
                'Value': instance_id
            },
        ],
        StartTime=start_time,   #over the 5-minute time window specified by start_time and end_time
        EndTime=end_time,  
        Period=300,        #Period parameter specifies that the metric should be aggregated over 5-minute intervals (which matches the length of the time window). 
        Statistics=[       #The Statistics parameter specifies that we are interested in the average value of the metric.
            'Average',
        ]
    )
    datapoints = response['Datapoints']  #extracts the list of datapoints returned by the metric query from the response object.
    if datapoints:
        return round(datapoints[0]['Average'], 2)
    else:
        return 0          #checks if there were any datapoints returned by the metric query. If there were, it returns the rounded average value of the first datapoint (which corresponds to the most recent 5-minute interval). If there were no datapoints returned, it returns 0.


def get_ram_utilization(instance_id):
    cloudwatch = boto3.client('cloudwatch')
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(minutes=5)
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='MemoryUtilization',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance_id
            },
        ],
        StartTime=start_time.isoformat(),
        EndTime=end_time.isoformat(),
        Period=300,
        Statistics=[
            'Average',
        ]
    )
    datapoints = response['Datapoints']
    if datapoints:
        return round(datapoints[0]['Average'], 2)
    else:
        return 0