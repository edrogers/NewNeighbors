#!/usr/bin/python

import requests
from time import sleep
import json
import re
import glob, os
from datetime import datetime, date
import config
from difflib import unified_diff

def send_email(user, pwd, recipient, subject, body):                                                                            
    import smtplib                                                                                                              
                                                                                                                                
    gmail_user = user                                                                                                           
    gmail_pwd = pwd                                                                                                             
    FROM = user                                                                                                                 
    TO = recipient if type(recipient) is list else [recipient]                                                                
    SUBJECT = subject                                                                                                           
    TEXT = body                                                                                                                 
                                                                                                                                
    # Prepare actual message                                                                                                    
    message = """\From: %s\nTo: %s\nSubject: %s\n\n%s                                                                           
    """ % (FROM, ", ".join(TO), SUBJECT, TEXT)                                                                                  
    try:                                                                     
        # SMTP_SSL Example
        server_ssl = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server_ssl.ehlo() # optional, called by login()
        server_ssl.login(gmail_user, gmail_pwd)
        # ssl server doesn't support or need tls, so don't call server_ssl.starttls()
        server_ssl.sendmail(FROM, TO, message)
        #server_ssl.quit()
        server_ssl.close()
        print 'successfully sent the mail'
    except:                                                                  
        print "failed to send mail"                                                                                             

#First, download all the parcels in Ward 79
httpRequestURL="https://data.cityofmadison.com/resource/u7ns-6d4x.csv?ward=79&$limit=5000"
headers={'X-App-Token': config.cityOfMadisonToken}

dirName=os.path.dirname(os.path.realpath(__file__))

r=requests.get(httpRequestURL,headers=headers)
filename = "Assessor_Property_Information.csv"
try:
    os.remove(filename)
except OSError:
    pass
fileout = open(filename,'wb')
fileout.write(r.content)
fileout.close()

logfilename = "errorlog.txt"

now = datetime.now()
csvfilename = "OwnerListing_{dt:%Y%m%d}.csv".format(dt=datetime.now())

try:
    os.remove(csvfilename)
except OSError:
    pass

#Next, use the parcel numbers & the city website to find the owners' names
parcelNumRE=re.compile("[0-9]{12}")
parcelAndAddressRE=re.compile("[0-9]{12},[^,]+")
for line in open(filename) :
    parcelAndAddressObject = parcelAndAddressRE.match(line)
    if parcelAndAddressObject != None:
        parcelAndAddress = parcelAndAddressObject.group(0).replace(',',';')
        parcelNum = parcelNumRE.match(parcelAndAddress).group(0)

        # Download by HTTP a parcel lookup from the city
        success = False
        attempts = 0
        while not success and attempts < 3 :
            try :
                resp = requests.get("http://www.cityofmadison.com/assessor/property/propertydata.cfm?ParcelN={}".format(parcelNum))
                success = True
            except requests.exceptions.RequestException as e :
                attempts += 1
                logfile = open(logfilename,'a')
                if attempts == 3 :
                    className = "ERROR:"
                else:
                    sleep(60)
                    className = "warn:"
                logfile.write("{} {dt:%c}; Parcel# {}; Attempt#: {}; {}: {}\n".format(className,parcelNum,attempts,type(e),e,dt=datetime.now()))
                logfile.close()

        # Save that content to a local file
        filename = "Madison_Parcel_{}.html".format(parcelNum)
        fileout = open(filename,'wb')
        fileout.write(resp.content)
        fileout.close()
        # Now open that file for reading
        filein = open(filename,'r')
        lines = filein.readlines()
        # Read the line that has the Owner's name(s)
        ownerNames=lines[257].strip()
        # Close and delete the file
        filein.close()
        try:
            os.remove(filename)
        except OSError:
            pass
        # Make that name more legible and replace semicolons with double commas
        ownerNamesPretty=ownerNames.replace('&amp;','&').replace('<br> ','').replace(';',',,')
        # Append the result to a CSV of parcel numbers and owner names
        # separated by semicolons
        csvOut = open(csvfilename,'a')
        csvOut.write("{};{}\n".format(parcelAndAddress,ownerNamesPretty))
        csvOut.close()
        # Impose a brief pause as a courtesy to the city
        sleep(4)


lastCSVEntryRE=re.compile("[^;]+$")
betweenSemicolons=re.compile(";[^;]+;")

# Now compare the two most recent Owner Listings for any changes:
ownerListingFiles = sorted(glob.glob(dirName+"/OwnerListing_*.csv"))
emailBodyLines = []
emailBodyLines.append("Hello,")
emailBodyLines.append("")
emailBodyLines.append("This is the automatically generated email to notify of changes to parcel listings on the City of Madison website.")
emailBodyLines.append("")

if len(ownerListingFiles) > 1 :
    previousFileName = ownerListingFiles[-2]
    currentFileName = ownerListingFiles[-1]
    prevDate = "{}-{}-{}".format(previousFileName[-8:-6],previousFileName[-6:-4],previousFileName[-12:-8])
    currDate = "{}-{}-{}".format(currentFileName[-8:-6],currentFileName[-6:-4],currentFileName[-12:-8])
    # print "Previous file : {}".format(previousFileName)
    # print "Current file  : {}".format(currentFileName)
    previousFile=open(previousFileName,'r')
    currentFile=open(currentFileName,'r')
    prev=previousFile.readlines()
    curr=currentFile.readlines()
        
    diff=unified_diff(prev,curr,lineterm='',n=0)

    lines = list(diff)[2:]
    prevLines = [line[1:] for line in lines if line[0] == '-']
    currLines = [line[1:] for line in lines if line[0] == '+']

    parcelsChanged = []
    parcelsRemoved = []
    parcelsAdded   = []
    for prevLine in prevLines :
        prevParcelNum = parcelNumRE.match(prevLine).group(0)
        prevAddress = betweenSemicolons.search(prevLine).group(0).strip(';')
        prevOwner = lastCSVEntryRE.search(prevLine).group(0).rstrip('\n')
        matchedThisParcelYet = False
        for currLine in currLines :
            currParcelNum = parcelNumRE.match(currLine).group(0)
            currAddress = betweenSemicolons.search(currLine).group(0).strip(';')
            currOwner = lastCSVEntryRE.search(currLine).group(0).rstrip('\n')
            if prevParcelNum == currParcelNum :
                matchedThisParcelYet = True
                parcelsChanged.append([prevParcelNum,prevAddress,prevOwner,currAddress,currOwner])
                break
        if matchedThisParcelYet == False :
            parcelsRemoved.append([prevParcelNum,prevAddress,prevOwner])
    for currLine in currLines :
        currParcelNum = parcelNumRE.match(currLine).group(0)
        currAddress = betweenSemicolons.search(currLine).group(0).strip(';')
        currOwner = lastCSVEntryRE.search(currLine).group(0).rstrip('\n')
        matchedThisParcelYet = False
        for prevLine in prevLines :
            prevParcelNum = parcelNumRE.match(prevLine).group(0)
            if prevParcelNum == currParcelNum :
                matchedThisParcelYet = True
        if matchedThisParcelYet == False :
            parcelsAdded.append([currParcelNum,currAddress,currOwner])

    if len(parcelsChanged) > 0 :
        emailBodyLines.append("")
        emailBodyLines.append("The following {} parcel(s) have changed:".format(len(parcelsChanged)))
        emailBodyLines.append("")
        for pC in parcelsChanged :
            emailBodyLines.append("Parcel #: {}".format(pC[0]))
            emailBodyLines.append("Owner:   {} --> {}".format(pC[2],pC[4]))
            emailBodyLines.append("Address: {} --> {}".format(pC[1],pC[3]))
            emailBodyLines.append("")
    if len(parcelsRemoved) > 0 :
        emailBodyLines.append("")
        emailBodyLines.append("The following {} parcel(s) have been removed from the city listing:".format(len(parcelsRemoved)))
        emailBodyLines.append("")
        for pC in parcelsRemoved :
            emailBodyLines.append("Parcel #: {}".format(pC[0]))
            emailBodyLines.append("Owner:   {}".format(pC[2]))
            emailBodyLines.append("Address: {}".format(pC[1]))
            emailBodyLines.append("")
    if len(parcelsAdded) > 0 :
        emailBodyLines.append("")
        emailBodyLines.append("The following {} parcel(s) have been added to the city listing:".format(len(parcelsAdded)))
        emailBodyLines.append("")
        for pC in parcelsAdded :
            emailBodyLines.append("Parcel #: {}".format(pC[0]))
            emailBodyLines.append("Owner:   {}".format(pC[2]))
            emailBodyLines.append("Address: {}".format(pC[1]))
            emailBodyLines.append("")

    previousFile.close()
    currentFile.close()

    if len(parcelsChanged)+len(parcelsAdded)+len(parcelsRemoved) > 0 :
        emailBodyLines.append("This email shows updates to the City of Madison Parcel Listings that occurred between {} and {}.".format(prevDate, currDate))
        emailBodyLines.append("")
        subjectLine = "Parcel Listing Updates for {dt:%B} {dt:%Y}".format(dt=datetime.now())
        emailBody = "\r\n".join(emailBodyLines)
        print subjectLine
        print emailBody
        send_email(config.gmailAddress,
                   config.gmailPassword,
                   config.targetAddress,
                   subjectLine,
                   emailBody)
    

quit()
