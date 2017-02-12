#!/usr/bin/python

import requests
from time import sleep
import json
import re
import glob, os
from datetime import datetime, date
import config
from difflib import unified_diff
import errno
from collections import Counter

dirName=os.path.dirname(os.path.realpath(__file__))

logfilename = "{}/errorlog.txt".format(dirName)

def downloadWithReattempts(url,nAttempts,timeDelay,logFileName):
    success = False
    attempts = 0
    while not success and attempts < nAttempts :
        success = True
        try :
            resp = requests.get(url)
        except requests.exceptions.RequestException as e :
            success = False
            attempts += 1
            with open(logFileName,'a') as logfile:
                if attempts == nAttempts :
                    className = "ERROR:"
                else:
                    sleep(timeDelay)
                    className = "warn:"
                logfile.write("{} {dt:%c}; Parcel# {}; Attempt#: {}; {}: {}\n".format(className,parcelNum,attempts,type(e),e,dt=datetime.now()))
    return resp

def getLineNumber():
    parcelNum="070930104032"
    examplePropertyListingURL="http://www.cityofmadison.com/assessor/property/propertydata.cfm?ParcelN={}".format(parcelNum)
    resp = downloadWithReattempts(examplePropertyListingURL,5,60,logfilename)

    filename = "{}/Madison_Parcel_{}.html".format(dirName,parcelNum)
    with open(filename,'wb') as fileout:
        fileout.write(resp.content)

    with open(filename,'r') as filein:
        lines = filein.readlines()
        # Fine the line number that has the Owner's name(s)
        linesWithOwnerNames=[ i for i,line in enumerate(lines) if 'EDWIN L ROGERS' in line ]

    try:
        os.remove(filename)
    except BaseException as e:
        logfile = open(logfilename,'a')
        className = "ERROR:"
        logfile.write("{} {dt:%c}; {}: {}\n".format(className,type(e),e,dt=datetime.now()))
        logfile.close()
        raise

    if len(linesWithOwnerNames) > 0:
        return linesWithOwnerNames[0]
    else:
        raise IndexError("Line with Owner Name not found")

def getArea(address):
    addressToAreaFileName="AddressAreaBlock.csv"
    with open(addressToAreaFileName,'r') as addressToAreaFile:
        lines=addressToAreaFile.readlines()
        areasWithThisAddress=[ re.search(",[0-9]+,",line.strip()).group().strip(",") for line in lines if address in line ]
    if len(areasWithThisAddress) > 0:
        return areasWithThisAddress[0]
    else:
        return "N/A"

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
        # print 'successfully sent the mail'
    except Exception as e:                                                                  
        logfile = open(logfilename,'a')
        className = "ERROR:"
        logfile.write("{} {dt:%c}; {}: {}\n".format(className,type(e),e,dt=datetime.now()))
        logfile.close()
        raise

lineNumForOwner=getLineNumber()

#First, download all the parcels in Ward 79
httpRequestURL="https://data.cityofmadison.com/resource/u7ns-6d4x.csv?ward=79&$limit=5000"
headers={'X-App-Token': config.cityOfMadisonToken}

r=requests.get(httpRequestURL,headers=headers)
filename = "{}/Assessor_Property_Information.csv".format(dirName)
with open(filename,'wb') as fileout:
    fileout.write(r.content)

now = datetime.now()
csvfilename = "{}/OwnerListing_{dt:%Y%m%d}.csv".format(dirName, dt=datetime.now())

try:
    os.remove(csvfilename)
except OSError as e:
    if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
        logfile = open(logfilename,'a')
        className = "ERROR:"
        logfile.write("{} {dt:%c}; {}: {}\n".format(className,type(e),e,dt=datetime.now()))
        logfile.close()
        raise
    else :
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
        resp = downloadWithReattempts("http://www.cityofmadison.com/assessor/property/propertydata.cfm?ParcelN={}".format(parcelNum),5,60,logfilename)

        # Save that content to a local file
        filename = "{}/Madison_Parcel_{}.html".format(dirName,parcelNum)
        with open(filename,'wb') as fileout:
            fileout.write(resp.content)
        # Now open that file for reading
        with open(filename,'r') as filein:
            lines = filein.readlines()

        # Read the line that has the Owner's name(s)
        ownerNames=lines[lineNumForOwner].strip()

        try:
            os.remove(filename)
        except Exception as e:
            logfile = open(logfilename,'a')
            className = "ERROR:"
            logfile.write("{} {dt:%c}; {}: {}\n".format(className,type(e),e,dt=datetime.now()))
            logfile.close()
            raise
        # Make that name more legible and replace semicolons with double commas
        ownerNamesPretty=ownerNames.replace('&amp;','&').replace('<br> ','').replace(';',',,')
        # Append the result to a CSV of parcel numbers and owner names
        # separated by semicolons
        csvOut = open(csvfilename,'a')
        csvOut.write("{};{}\n".format(parcelAndAddress,ownerNamesPretty))
        csvOut.close()
        # Impose a brief pause as a courtesy to the city
        sleep(5)

# Check for any parcels that have changed from the previous listing.
# For each changed parcel, re-download the parcel listing a few more times
# to verify beyond a doubt the listing is indeed different (and not a
# connection issue).

lastCSVEntryRE=re.compile("[^;]+$")
betweenSemicolons=re.compile(";[^;]+;")

# Now compare the two most recent Owner Listings for any changes:
ownerListingFiles = sorted(glob.glob(dirName+"/OwnerListing_*.csv"))

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
    previousFile.close()
    currentFile.close()
        
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
                if prevOwner == currOwner :
                    # For address changes, go ahead and report the change immediately
                    parcelsChanged.append([prevParcelNum,prevAddress,prevOwner,currAddress,currOwner])
                    break
                else :
                    # For owner changes, recheck the owner a few times before reporting
                    newOwnersList = ([currOwner])

                    for i in range(4) :
                        #Each download will make 5 attempts to avoid RequestException, as usual
                        resp = downloadWithReattempts("http://www.cityofmadison.com/assessor/property/propertydata.cfm?ParcelN={}".format(currParcelNum),5,60,logfilename)

                        # Save that content to a local file
                        filename = "{}/Madison_Parcel_{}.html".format(dirName,currParcelNum)
                        with open(filename,'wb') as fileout:
                            fileout.write(resp.content)

                        # Now open that file for reading
                        with open(filename,'r') as filein:
                            lines = filein.readlines()

                        # Read the line that has the Owner's name(s)
                        ownerNames=lines[lineNumForOwner].strip()

                        try:
                            os.remove(filename)
                        except Exception as e:
                            logfile = open(logfilename,'a')
                            className = "ERROR:"
                            logfile.write("{} {dt:%c}; {}: {}\n".format(className,type(e),e,dt=datetime.now()))
                            logfile.close()
                            raise
                        # Make that name more legible and replace semicolons with double commas
                        ownerNamesPretty=ownerNames.replace('&amp;','&').replace('<br> ','').replace(';',',,')

                        newOwnersList.append(ownerNamesPretty)
                        sleep(60)

                    # Code to select the mode of the 5 elements of newestReadings goes here
                    newOwnerCounter = Counter(newOwnersList)
                    trueNewOwner = newOwnerCounter.most_common(1)[0][0]
                    if trueNewOwner != currOwner :
                        # Need to update OwnerListing_[date].csv
                        with open(currentFileName, "r") as fileToEdit:
                            linesToEdit = fileToEdit.readlines()
                        with open(currentFileName, "w") as fileToEdit:
                            for lineToEdit in linesToEdit:
                                fileToEdit.write(lineToEdit.replace('{};{};{}'.format(currParcelNum,currAddress,currOwner),
                                                                    '{};{};{}'.format(currParcelNum,currAddress,trueNewOwner)))
                        currOwner = trueNewOwner

                    if prevOwner != currOwner or prevAddress != currAddress :
                        # This owner change seems legit, go ahead and report it
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

    emailBodyLines = []
    emailBodyLines.append("Hello,")
    emailBodyLines.append("")
    emailBodyLines.append("This is the automatically generated email to notify of changes to parcel listings on the City of Madison website.")
    emailBodyLines.append("")

    if len(parcelsChanged) > 0 :
        emailBodyLines.append("")
        emailBodyLines.append("The following {} parcel(s) have changed:".format(len(parcelsChanged)))
        emailBodyLines.append("")
        for area in range(17):
            thisAreaIntroduced=False
            for pC in parcelsChanged :
                strArea=str(area)
                if area==16:
                    strArea="N/A"
                if getArea(pC[3]) == strArea :
                    if not thisAreaIntroduced :
                        if area != 16:
                            emailBodyLines.append("Area {}:".format(area))
                        else :
                            emailBodyLines.append("Other:".format(area))
                        thisAreaIntroduced=True
                    if pC[1]==pC[3]:
                        emailBodyLines.append("  {}".format(pC[3]))
                        emailBodyLines.append("    Previous owner:   {}".format(pC[2]))
                        emailBodyLines.append("    New owner:        {}".format(pC[4]))
                    else:
                        emailBodyLines.append("  Changes to parcel #: {}".format(pC[0]))
                        emailBodyLines.append("    Owner:   {} --> {}".format(pC[2],pC[4]))
                        emailBodyLines.append("    Address: {} --> {}".format(pC[1],pC[3]))
            if thisAreaIntroduced:
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

    if len(parcelsChanged)+len(parcelsAdded)+len(parcelsRemoved) > 0 :
        if len(parcelsChanged)+len(parcelsAdded)+len(parcelsRemoved) > 100 :
            message=["THIS EMAIL WAS NOT SENT! SUSPICIOUS OUTPUT DETECTED",""]
            message.extend(emailBodyLines)
            subjectLine = "UNSENT: Parcel Listing Updates for {dt:%B} {dt:%Y}".format(dt=datetime.now())
            emailBody = "\r\n".join(message)
            send_email(config.gmailAddress,
                       config.gmailPassword,
                       config.gmailAddress,
                       subjectLine,
                       emailBody)
        else : 
            emailBodyLines.append("This email shows updates to the City of Madison Parcel Listings that occurred between {} and {}.".format(prevDate, currDate))
            emailBodyLines.append("")
            subjectLine = "Parcel Listing Updates for {dt:%B} {dt:%Y}".format(dt=datetime.now())
            emailBody = "\r\n".join(emailBodyLines)
            send_email(config.gmailAddress,
                       config.gmailPassword,
                       config.targetAddress,
                       subjectLine,
                       emailBody)

quit()
