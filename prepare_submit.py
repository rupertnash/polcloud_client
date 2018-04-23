import argparse
import json
import os
import string
import sys
import time
from polcloud.client import Job, Pool

def get_gmy_filename_from_xml(xml_filename):
    from xml.etree import ElementTree
    tree = ElementTree.parse(xml_filename)
    gmy_filename = tree.getroot().find('geometry/datafile').attrib['path']
    return gmy_filename

def get_callback(file_name):
    total = os.path.getsize(file_name)
    def progress_callback(monitor):
        frac = monitor.bytes_read/total
        if frac > 1:
            frac = 1
        sys.stdout.write('\r[{:>7.2%}] '.format(frac))
        sys.stdout.flush()
    return progress_callback

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Create an Azure pool and submit job')
    parser.add_argument('xml_file', nargs='?', help='HemeLB XML input file')
    parser.add_argument('-s', '--spec', help='existing job spec')
    parser.add_argument('-p', '--pool', help='existing pool')
    parser.add_argument('-t', '--token', help='user token', required=True)
    parser.add_argument('-d', '--delete-pool', action='store_true', help='delete pool when job is complete')
    parser.add_argument('--upload-only', action='store_true', help='upload inputs only')
    args = parser.parse_args()

    job = Job()
    job.set_user(args.token)

    if args.spec:
        job.spec = args.spec
        job.inputs = job.get_job_spec()['inputs']
    else:
        # input files
        xml_file = args.xml_file
        gmy_file=get_gmy_filename_from_xml(xml_file)

        # upload input files in one step:
        # job.create_input(xml_file, gmy_file)

        # upload input files in several steps (if uploads are slow)
        job.create_input()
        print('Created input: %s' % job.inputs)
        print('Uploading %s' % xml_file)
        job.update_input(xml_file, get_callback(xml_file))
        print('\nUploading %s' % gmy_file)
        job.update_input(gmy_file, get_callback(gmy_file))
        print('\nInput complete.')
        print(json.dumps(job.get_input_info(), indent=4))

        # create a job spec
        with open('job_template.json') as f:
            job_spec = json.load(f)
        job_spec['inputs'] = job.inputs
        for command in job_spec['commands']:
            command['expression'] = \
                string.Template(command['expression']).substitute(
                    xml_file=xml_file,
                    gmy_file=gmy_file)
        print(json.dumps(job_spec, indent=4))

        job.create_job_spec(job_spec)
        print('Created job spec: %s' % job.spec)

    if args.pool:
        job.set_pool(args.pool)
    else:
        job.create_pool(size=2)
    print("Using pool: %s" % job.pool.get_info())

    print("Waiting for pool...")
    while not job.pool.is_ready():
        time.sleep(5)
    print('Pool is ready: submitting job...')
    job_id = job.submit(size=2, wall_clock='02:00')
    print('Submitted job: %s' % job_id)
    print('Waiting for job...')

    while not job.is_complete():
        time.sleep(5)

    print('Job is complete')
    print(json.dumps(job.list_outputs(), indent=4))

    if args.delete_pool:
        job.pool.delete()
        print('Deleted pool')
    else:
        print('Pool is running: %s' % job.pool.get_info())