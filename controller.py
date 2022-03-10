import boto3
import time
import configparser
import logging

config = configparser.ConfigParser()
config.read('/var/www/html/webtier/configuration.properties')
logging.basicConfig(filename='/var/www/html/webtier/webtier.log', level=logging.INFO)

resource_region = config['InstanceSection']['Region']

ec2_resource = boto3.resource('ec2',region_name = resource_region)
ec2_client   = boto3.client('ec2', region_name = resource_region)
sqs_resource = boto3.resource('sqs',region_name = resource_region)
sqs_client = boto3.client('sqs',region_name = resource_region)

queue_url = config['SQSSection']['SQS_Input_Queue_URL']

instance_limit = int(config['InstanceSection']['Instance_Limit'])
instancecounter = 0

# create single instance
def create_instance():
    logging.info("Creating instance")
    instances = ec2_resource.create_instances(
        ImageId=config['InstanceSection']['AMI_ID'],
        MinCount=1,
        MaxCount=1,
        InstanceType=config['InstanceSection']['AMI_Instance_Type'],
        KeyName='cc-1-37-key-pair'
    )
    apptier_prefix = config['InstanceSection']['AppTierInstanceNamePrefix']
    # naming the instances
    for instance in instances:
        global instancecounter
        ec2_client.create_tags(
            Resources=[
                instance.id,
            ],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': apptier_prefix + str(instancecounter + 1)
                },
            ]
        )
        instancecounter = (instancecounter + 1) % 19

    for instance in instances:
        instance.wait_until_running()
    return instances[0].id

# create multiple instances
def create_instances(n):
    
    instances = ec2_resource.create_instances(
        ImageId=config['InstanceSection']['AMI_ID'],
        MinCount=1,
        MaxCount=n,
        InstanceType=config['InstanceSection']['AMI_Instance_Type'],
        KeyName='cc-1-37-key-pair'
    )
    apptier_prefix = config['InstanceSection']['AppTierInstanceNamePrefix']
    # naming the instances
    for instance in instances:
        global instancecounter
        ec2_client.create_tags(
            Resources=[
                instance.id,
            ],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': apptier_prefix + str(instancecounter + 1)
                },
            ]
        )
        instancecounter = (instancecounter + 1) % 19

    for instance in instances:
        instance.wait_until_running()


# prints all the ec2 resources
def print_resources():
    for instance in ec2_resource.instances.all():
        logging.info(instance.id , instance.public_dns_name , instance.state['Name'])
        print (instance.id , instance.public_dns_name , instance.state['Name'])


# returns list of all the instance ids
def get_instances():
    l = []
    for instance in ec2_resource.instances.all():
        l.append(instance.id)
    return l

# returns list of all the instance ids that are running
def get_running_instances():
    l = []
    for instance in ec2_resource.instances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['running','pending']}]):
        l.append(instance.id)
    return l

# returns list of all the instance ids that are stopped
def get_idle_instances():
    l = []
    for instance in ec2_resource.instances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['stopped','stopping']}]):
        l.append(instance.id)
    return l

def get_stopped_instances():
    l = []
    for instance in ec2_resource.instances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['stopped']}]):
        l.append(instance.id)
    return l

# get single instance
def get_instance(instance_id):
    return ec2_resource.Instance(instance_id)

# terminate all instances
def terminate_all_instances():
    ec2_resource.instances.all().terminate()

# terminate multiple instances
def terminate_instances(ids):
    ec2_resource.instances.filter(InstanceIds = ids).terminate()

# terminate single instance
def terminate_instance(id):
    ec2_resource.instances.filter(InstanceIds = [id]).terminate()

# stop multiple instances
def stop_instances(ids):
    ec2_resource.instances.filter(InstanceIds = ids, Filters = [{'Name' : 'instance-state-name','Values' : ['running','pending']}]).stop()

# stop single instance
def stop_instance(id):
    ec2_resource.instances.filter(InstanceIds = [id], Filters = [{'Name' : 'instance-state-name','Values' : ['running','pending']}]).stop()

# start multiple instances
def start_instances(ids):
    ec2_resource.instances.filter(InstanceIds = ids, Filters = [{'Name' : 'instance-state-name','Values' : ['stopped','stopping']}]).start()

    for id in ids:
        instance = ec2_resource.Instance(id)
        instance.wait_until_running()

# start single instance
def start_instance(id):
    ec2_resource.instances.filter(InstanceIds = [id], Filters = [{'Name' : 'instance-state-name','Values' : ['stopped','stopping']}]).start()

# number of messages in the queue
def input_queue_length():
    queue = sqs_resource.Queue(queue_url)
    return int(queue.attributes.get('ApproximateNumberOfMessages'))

# function to find the mode 
def most_frequent(l): 
    return max(set(l), key = l.instancecounter) 

# wairs for all the instances to start
def waiter_function(ids):
    for id in ids:
        instance = ec2_resource.Instance(id)
        instance.wait_until_running()

if __name__=="__main__":

    while 1:

        # finding mode of 100 queue lengths
        ql = []
        x = 50
        while x:
            ql.append(input_queue_length())
            x -= 1
        # q_length = input_queue_length()
        q_length = most_frequent(ql)

        # get the number of active and idle instances
        active_instances = len(get_running_instances())
        idle_instances = len(get_idle_instances())

        # print('--------------------------------------------------------')
        # print('queue length', q_length)
        # print('active instances:', active_instances)
        # print('idle instances:', idle_instances)
        # print('--------------------------------------------------------')

        # if the queue length is 0 then continue polling the queue for any messages
        if q_length == 0:
            time.sleep(20)
            continue

        # if queue length is more than 19 then we have to start/create instances upto 19
        elif q_length > instance_limit:

            # create any instance if needed
            if instance_limit - active_instances - idle_instances > 0:
                create_instances(instance_limit - active_instances - idle_instances)
            # start all the idle instances
            if idle_instances > 0:
                l = []
                while idle_instances:
                    if len(get_stopped_instances()) > 0:
                        temp = get_stopped_instances()[0]
                        if temp not in l:
                            start_instance(temp)
                            l.append(temp)
                            idle_instances -= 1
                waiter_function(l)
        
        # if queue length is greater than the number of idle instances, we need to start all the idle instances and create new ones if needed
        elif q_length > idle_instances:

            # create instances if needed
            if (idle_instances + active_instances + (q_length - idle_instances)) <= instance_limit and (q_length - idle_instances) > 0:
                create_instances(q_length - idle_instances)
            else:
                if instance_limit - active_instances - idle_instances > 0:
                    create_instances(instance_limit - active_instances - idle_instances)
            # start the idle instances
            if idle_instances > 0: 
                l = []
                while idle_instances:
                    if len(get_stopped_instances()) > 0:
                        temp = get_stopped_instances()[0]
                        if temp not in l:
                            start_instance(temp)
                            l.append(temp)
                            idle_instances -= 1
                waiter_function(l)
            
        # if queue length is less than the number of idle isntances, start the necessary number of idle instances
        elif q_length <= idle_instances:

            # start the necessary idle instances
            l = []
            while q_length > 0:
                if len(get_stopped_instances()) > 0:
                    temp = get_stopped_instances()[0]
                    if temp not in l:
                        start_instance(temp)
                        print(temp)
                        l.append(temp)
                        q_length -= 1
            waiter_function(l)

        time.sleep(20)


        
        
