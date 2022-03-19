import boto3
import time
import configparser
import logging

config = configparser.ConfigParser()
config.read('./configuration.properties')
logging.basicConfig(filename='./webtier-1.log', level=logging.INFO, 
    format="%(asctime)s %(levelname)s %(threadName)s %(name)s %(message)s")

resource_region = config['InstanceSection']['Region']

ec2 = boto3.resource('ec2',region_name = resource_region)
ec2Client = boto3.client('ec2', region_name = resource_region)
sqs = boto3.resource('sqs',region_name = resource_region)

inputQueueUrl = config['SQSSection']['SQS_Input_Queue_URL']

instanceLimit = int(config['InstanceSection']['Instance_Limit'])

# Create Instances
def createInstances(instancesToCreate):
    logging.info("Creating " + str(instancesToCreate) + " instance(s)")
    instances = ec2.create_instances(
        ImageId = config['InstanceSection']['AMI_ID'],
        MinCount = 1,
        MaxCount = instancesToCreate,
        InstanceType = config['InstanceSection']['AMI_Instance_Type'],
        KeyName = 'cc-1-37-key-pair',
        SecurityGroupIds=['sg-0da833c2c14b49621']
    )

    apptierPrefix = config['InstanceSection']['AppTierInstanceNamePrefix']
    instanceCounter = 0

    for instance in instances:
        ec2Client.create_tags(
            Resources=[
                instance.id,
            ],
            Tags=[
                {
                    'Key': 'Name',
                    'Value': apptierPrefix + str(instanceCounter + 1)
                },
            ]
        )
        instance.wait_until_running()
        instanceCounter = (instanceCounter + 1) % 19

def startIdleInstances(idleInstancesToStart, idleInstances):
    # Start all the idle instances
    logging.info("Starting " + str(idleInstancesToStart) + " instance(s)")
    for i in range(idleInstancesToStart):
        instance = idleInstances[i]
        if instance.state['Name'] == 'stopping':
            instance.wait_until_stopped()
        instance.start()
    for i in range(idleInstancesToStart):
        instance = idleInstances[i]
        instance.wait_until_running()

if __name__=="__main__":

    while True:
        queue = sqs.Queue(inputQueueUrl)
        queueLength =  int(queue.attributes.get('ApproximateNumberOfMessages'))
        logging.info(str(queueLength) + " Message(s) in Input Queue")
        allInstances = ec2.instances.all()
        
        activeInstances = allInstances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['running','pending']}])
        activeInstances = list(activeInstances)
        stoppedInstances = allInstances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['stopped']}])
        stoppingInstances = allInstances.filter(Filters = [{'Name' : 'instance-state-name','Values' : ['stopping']}])
        idleInstances = list(stoppedInstances) + list(stoppingInstances)
        idleInstancesCount = len(idleInstances)
        existingInstancesCount = len(activeInstances) + idleInstancesCount

        # If Queue length is less than or same as number of idle instances, start as many idle instances as the queue length
        if queueLength <= idleInstancesCount and queueLength > 0:
            #Start Idle Instances
            startIdleInstances(queueLength, idleInstances)

        # If Queue length is more than the number of idle instances
        elif queueLength > idleInstancesCount:
            # Start Idle Instances
            if idleInstancesCount > 0:
                startIdleInstances(idleInstancesCount, idleInstances)
                queueLength -= idleInstancesCount
            
            instancesToCreate = 0
            # If Queue length is greater than free tier instance limit, create as many instances as the 
            # instance limit while keeping a tab on existing instances
            if queueLength > instanceLimit and instanceLimit > existingInstancesCount:
                instancesToCreate = instanceLimit - existingInstancesCount
            # If Queue length is less than instance limit but more than idle instances create as many instances
            # as the queue length other than the idle instances while keeping a tab on the active instances
            elif queueLength + existingInstancesCount <= instanceLimit:
                instancesToCreate = queueLength
            
            # Create Instances if required
            if instancesToCreate > 0:
                createInstances(instancesToCreate)

        time.sleep(20)
