# -*- coding: utf-8 -*-
"""
Created on Tue Feb 23 14:34:33 2016

@author: bijalwan_n
"""
from novaclient import client as nvclient
from cinderclient.v2 import client as cinclient
import logging
import logging.handlers
import os
import sys
import getpass
from time import gmtime, strftime

os.environ["OS_VOLUME_API_VERSION"] = "2"

def generate_logger():
    logger = logging.getLogger()
    fh = logging.handlers.RotatingFileHandler('./backup.log', maxBytes=10485760, backupCount=5)
    fh.setLevel(logging.WARN)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.setLevel(logging.WARN)
    return logger
 
def main(argv):
    detachedVolumes={}
    try:
        backuplog = generate_logger()
        
        pswd = getpass.getpass('Password:')
        
        username=argv[0]
        tenantname=argv[1]
        password=pswd
        authurl=argv[2]
        mailto=None
        if argv[3]:
		mailto=argv[3]
        
        print "In Progress"
        
        nt = nvclient.Client("2", username, password, tenantname, authurl)
        
        servers=nt.servers.list(search_opts={'all_tenants': 1})
        
        #print servers[0].tenant_id
        if not detachedVolumes:
          for server in servers:
            volumes=nt.volumes.get_server_volumes(server.id)
            for vol1 in volumes:
                device = getattr(vol1, 'device')
                ntvolume=nvclient.Client("2", username, password, tenantname, authurl,service_type = 'volume')
                vol=ntvolume.volumes.get(vol1.id)
                owner_tenant_id = getattr(vol, 'os-vol-tenant-attr:tenant_id')
                bootable = getattr(vol, 'bootable')
                #volume_type = getattr(vol, 'volume_type')
                #print server.id, '  ', owner_tenant_id, ' ',bootable, server.tenant_id, '  ', server.name , '  ' , server.status
                if server.tenant_id==owner_tenant_id and bootable == 'false' and server.status=='SHUTOFF' and vol.name != None :
                    #print server.id, '  ', server.tenant_id, '  ', server.name, '  ', server.status, '  ', vol.name,'  ', vol.id, '  ', vol.status , '  ' , device , '  ' ,volume_type, '  ' , vol1.volumeId      
                    vm = nt.servers.get(server.id)
                    #print vm
                    backuplog.warn("Detaching Volume id : " + vol1.id + " from server id: " +  server.id)
                    nt.volumes.delete_server_volume(vm.id, vol1.id)
                    #print "Deleting volume"
                    cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                    cindclient.volumes.detach(vol1.id)
                    detachedVolumes[vol1.id]={'serverid':server.id,'servername':server.name,'volname':vol.name,'device':device,'state' : 'detaching'}
        
        allAttached=False
        
        while not allAttached and detachedVolumes:
            #print "inside while"
            allAttached=True
            
            for dVol in detachedVolumes:              
              if detachedVolumes[dVol]['state'] != 'attached':
                 allAttached=False;
               
            for dVol in detachedVolumes:
              
              if allAttached:
                  break;
                  
              if detachedVolumes[dVol]['state'] == 'detaching':     
                 #print "inside detaching"
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                 volume=cindclient.volumes.get(dVol)      
                 #print "inside after detaching"
                 #print 'volume.status ' + volume.status
                 if volume.status == 'available':
                     backuplog.warn("Successfully Detached Volume id : " + dVol + " from server id: " +  detachedVolumes[dVol]['serverid'])
                     detachedVolumes[dVol]['state']='detached'
                 if volume.status == 'error':
                     backuplog.warn("Error while Detaching Volume id : " + dVol + " from server id: " +  detachedVolumes[dVol]['serverid'])
                     detachedVolumes[dVol]['state']='backupcompleted' 
                 
              if detachedVolumes[dVol]['state'] == 'detached':   
                
                 #serverid = detachedVolumes[dVol]['serverid']
                 servername=detachedVolumes[dVol]['servername']
                 volname = servername + "_" + strftime( "%d-%m-%Y-%H:%M:%S", gmtime()) #detachedVolumes[dVol]['volname']
                 device = detachedVolumes[dVol]['device']
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                 volume=cindclient.volumes.get(dVol)  
                 #print dir(volume)
                 tenant_id = getattr(volume, 'os-vol-tenant-attr:tenant_id')
                 #print 'tenant_id ' +  tenant_id
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=tenant_id,auth_url=authurl)
                 backupvol = cindclient.backups.create(dVol,name=volname)       
                 #print 'backupvolid: ' + vol.id    
                 detachedVolumes[dVol]['backupvolid'] = backupvol.id
                 backuplog.warn("Creatingbackup for Backup : " + backupvol.id + " for volume id: " +  dVol)
                 
                 detachedVolumes[dVol]['state']= 'creatingbackup'
                 
              if detachedVolumes[dVol]['state'] == 'creatingbackup':
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                 volume=cindclient.volumes.get(dVol)  
                 #print dir(volume)
                 tenant_id = getattr(volume, 'os-vol-tenant-attr:tenant_id')
                 #print 'tenant_id ' +  tenant_id
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=tenant_id,auth_url=authurl)
                 backup = cindclient.backups.get(detachedVolumes[dVol]['backupvolid'])
                 #print backup.id + " = " + backup.status
                 if backup.status == 'available':
                     backuplog.warn("Successfully Created Backup : " + detachedVolumes[dVol]['backupvolid'] + "  for volume id: " +  dVol)
                     detachedVolumes[dVol]['state']='backupcompleted' 
                 if backup.status == 'error':
                     backuplog.error("Error while creating Backup : " + detachedVolumes[dVol]['backupvolid'] + "  for volume id: " +  dVol)
                     detachedVolumes[dVol]['state']='backupcompleted' 
                     
              if detachedVolumes[dVol]['state'] == 'backupcompleted':
                 vm = nt.servers.get(detachedVolumes[dVol]['serverid'])
                 #print "Attaching Volume id : " + dVol + " to server : '" + detachedVolumes[dVol]['serverid'] + "' and device ' " + detachedVolumes[dVol]['device'] + "'"
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                 volume=cindclient.volumes.get(dVol)  
                 tenant_id = getattr(volume, 'os-vol-tenant-attr:tenant_id')    
                 #cindclient = cinclient.Client(username=username, api_key=password, tenant_id=tenant_id,auth_url=authurl)
                 #cindclient.volumes.attach(volume , dVol, detachedVolumes[dVol]['device'])     
                 nt.volumes.create_server_volume(vm.id, dVol, detachedVolumes[dVol]['device'])     
                 detachedVolumes[dVol]['state']= 'attaching' 
                 backuplog.warn("Attaching Volume id : " + dVol + " to server : '" + detachedVolumes[dVol]['serverid'] + "' and device ' " + detachedVolumes[dVol]['device'] + "'")
            
              if detachedVolumes[dVol]['state'] == 'attaching':         
                 cindclient = cinclient.Client(username=username, api_key=password, tenant_id=owner_tenant_id,auth_url=authurl)
                 volume=cindclient.volumes.get(dVol)  
                 if volume.status == 'in-use':          
                    backuplog.warn("Successfully Attached volume id: " +  dVol + "  to device: " +  detachedVolumes[dVol]['device'])
                    detachedVolumes[dVol]['state']= 'attached' 
                 if volume.status == 'error':
                     backuplog.error("Error while attaching volume id: " +  dVol + "  to device: " +  detachedVolumes[dVol]['device'])
                     detachedVolumes[dVol]['state']='backupcompleted' 
                    
        backuplog.info("Backup Process Completed ")             
    
    except Exception, e:
        backuplog.error(e.message)
    finally:
        message = " Backed up volume/volumes are:"
        message = message + "\r\n" + " Volume Name       |        Volume ID"
        message = message + "\r\n" +  " -------------------------------------------------------------------------------"
        totalbackedupvolumes=0
        for dVol in detachedVolumes:
            if detachedVolumes[dVol]['state']=='backupcompleted' or detachedVolumes[dVol]['state']=='attached':
                totalbackedupvolumes=totalbackedupvolumes+1
                message = message + "\r\n " + detachedVolumes[dVol]['volname'] + "      |       " + dVol
        message = message + "\r\n " + "-------------------------------------------------------------------------------"
        message = message + "\r\n " + "Number of volume/volumes are backed up: " + str(totalbackedupvolumes) 
        
        print message
        
        subject = "Cinder Backup " + strftime( "%d-%m-%Y-%H:%M:%S", gmtime()) 
        
        if mailto:
           response=os.system('echo "' + message + '" | mail -s "' + subject + '" ' + mailto)
           if response==0:
               backuplog.warn("Email sent successfully" )
               print "Email sent successfully"       
           else:
               backuplog.warn("Error while sending email")
               print "Error while sending email"  
        
        backuplog.warn("Done")
        print "Done"
    
if __name__ == "__main__":
   main(sys.argv[1:])   
   
#print detachedVolumes