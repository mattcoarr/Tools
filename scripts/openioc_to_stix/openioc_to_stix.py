# Note: You need to run the following command to add the bindings to your load path:
# export PYTHONPATH=stix:stix/capec:stix/cybox:stix/cvrf:stix/iodef:stix/maec:stix/oasis

from openioc_to_cybox import OpeniocToCybox
import sys
import os
import traceback
import ioc_observable
import openioc
import uuid
import glob
from stix import stix_core_1_0 as stix
from stix import stix_indicator_1_1 as stix_indicator_package
import cybox_common_types_1_0 as cybox_common
import cybox_core_1_0 as cybox

USAGE_TEXT = """
OpenIOC --> STIX XML Converter Utility
v0.1 BETA // Compatible with CybOX v1.0 and STIX 1.0-draft3

Usage: python openioc_to_stix.py <flags> -i <openioc xml file> -o <stix xml file>

Available Flags:
    -v: Verbose output mode. Lists any skipped indicator items and also prints traceback for errors.
    -n: ID namespace to use
    -p: ID prefix to use
    -O: Generate CybOX observables in addition to indicators
    -T: Include source OpenIOC as a TestMechanism in the indicator
"""

# Override the export method on the observables type so that it doesn't output the namespaces
class StixObservablesType(cybox.ObservablesType):
    def export(self, outfile, level, namespace_='cybox:', name_='Observables', namespacedef_='', pretty_print=True):
        if pretty_print:
            eol_ = '\n'
        else:
            eol_ = ''
        cybox.showIndent(outfile, level, pretty_print)
        #Build and set the namespace declarations so that we generate valid CybOX XML
        outfile.write('<%s%s%s' % (namespace_, name_, namespacedef_ and ' ' + namespacedef_ or '', ))
        already_processed = []
        self.exportAttributes(outfile, level, already_processed, namespace_, name_='ObservablesType')
        if self.hasContent_():
            outfile.write('>%s' % (eol_, ))
            self.exportChildren(outfile, level + 1, namespace_, name_, pretty_print=pretty_print)
            cybox.showIndent(outfile, level, pretty_print)
            outfile.write('</%s%s>%s' % (namespace_, name_, eol_))
        else:
            outfile.write('/>%s' % (eol_, ))


class OpeniocToStix(OpeniocToCybox):

    def __init__(self, namespace='http://example.com', prefix='example', verbose_mode=False, add_observables=True, add_test_mechanisms=True):
        self.prefix = prefix
        self.namespace = namespace
        self.verbose_mode = verbose_mode
        self.skipped_indicators = []
        self.obsv_id_base = 0
        self.obj_id_base = 0
        self.add_observables = True
        self.add_test_mechanisms = True

    def process_stix_package(self, indicator_files):
        #Create the core STIX structure
        package_id = self.prefix + ':package-' + self.generate_generic_id()
        package = stix.STIXType(id=package_id)
        stix_indicators = stix.IndicatorsType()
        observables = StixObservablesType(cybox_major_version=1,cybox_minor_version=0)

        package.set_Indicators(stix_indicators)

        if self.add_observables:
            package.set_Observables(observables)

        for indicator_file in indicator_files:
            indicators = openioc.parse(indicator_file)
            self.process_ioc_indicators(indicators, stix_indicators, observables)

        return package

    def process_ioc_indicators(self, indicators, stix_indicators, observables):
        indicator_definition = indicators.get_definition()
        for indicator in indicator_definition.get_Indicator():
            #Create the 'indicator' observable for holding the boolean indicator logic
            id_string = ''
            if indicator.get_id() is not None:
                id_string = self.prefix + ':indicator-' + self.normalize_id(indicator.get_id())
            else:
                id_string = self.prefix + ':indicator-' + generate_generic_id()
            stix_indicator = stix_indicator_package.IndicatorType(id=id_string)
            
            # Set the description as appropriate
            desc = cybox_common.StructuredTextType()
            stix_indicator.set_Description(desc)

            # If we have a short description, set that as a title
            if indicators.get_short_description != None:
                desc.add_Text_Title(indicators.get_short_description())

            # If we have a long description, set that as a text
            if indicators.get_description() != None:
                desc.add_Text(indicators.get_description())

            # Set indicator type from the link category
            for link in indicators.get_links().get_link():
                if link.get_rel() == "category":
                    stix_indicator.set_IndicatorType(stix_indicator_package.IndicatorTypeType(valueOf_=link.get_valueOf_()))


            composition = cybox.ObservableCompositionType(operator=indicator.get_operator())
            composition_observable = cybox.ObservableType(Observable_Composition=composition)
            composition_observables = stix_indicator_package.ObservablesType()
            composition_observables.add_Observable(composition_observable)

            # Process the indicator, including any embedded indicators
            self.process_indicator(indicator, observables, composition, True)

            # Add the OpenIOC content as a test mechanism, if applicable
            if self.add_test_mechanisms:
                self.add_test_mechanism(stix_indicator, indicators)

            if self.add_observables:
                stix_indicator.set_Observables(composition_observables)
            
            stix_indicators.add_Indicator(stix_indicator)

    def add_test_mechanism(self, stix_indicator, ioc):
        tms = stix_indicator_package.TestMechanismsType()
        tm = stix_indicator_package.TestMechanismType(type_="OpenIOC")
        tms.add_TestMechanism(tm)
        stix_indicator.set_TestMechanisms(tms)

    def generate_generic_id(self):
        return str(uuid.uuid4())

#Print the usage text    
def usage():
    print USAGE_TEXT
    sys.exit(1)

def get_files(directory):
    return glob.glob(directory + "/*.ioc")

def main():
    infolder = ''
    outfilename = ''

    verbose_mode = False
    add_observables = False
    add_test_mechanisms = False
    skipped_indicators = []
    namespace = "example.com"
    prefix = "example"
    
    #Get the command-line arguments
    args = sys.argv[1:]
    
    if len(args) < 4:
        usage()
        sys.exit(1)
        
    for i in range(0,len(args)):
        if args[i] == '-i':
            infolder = args[i+1]
        elif args[i] == '-o':
            outfilename = args[i+1]
        elif args[i] == '-n':
            namespace = args[i+1]
        elif args[i] == '-p':
            prefix = args[i+1]
        elif args[i] == '-v':
            verbose_mode = True
        elif args[i] == "-O":
            add_observables = True
        elif args[i] == "-T":
            add_test_mechanisms = True
            
    #Basic input file checking       
    try:
        files = get_files(infolder)
        print 'Generating ' + outfilename + ' from ' + str(len(files)) + ' IOCs in folder ' + infolder + '...'
        package = OpeniocToStix(namespace=namespace, prefix=prefix, verbose_mode=verbose_mode, add_observables=add_observables, add_test_mechanisms=add_test_mechanisms).process_stix_package(files)
        # TODO: How can we trim this down?? Kinda sucks to have unnecessary namespaces included by default in examples...
        namespacedef = """xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\
 xmlns:openioc="http://schemas.mandiant.com/2010/ioc"\
 xmlns:stix="http://stix.mitre.org"\
 xmlns:indicator="http://stix.mitre.org/Indicator"\
 xmlns:cybox="http://cybox.mitre.org/cybox_v1"\
 xmlns:AccountObj="http://cybox.mitre.org/objects#AccountObject"\
 xmlns:AddressObj="http://cybox.mitre.org/objects#AddressObject"\
 xmlns:Common="http://cybox.mitre.org/Common_v1"\
 xmlns:DiskObj="http://cybox.mitre.org/objects#DiskObject"\
 xmlns:DiskPartitionObj="http://cybox.mitre.org/objects#DiskPartitionObject"\
 xmlns:DNSRecordObj="http://cybox.mitre.org/objects#DNSRecordObject"\
 xmlns:FileObj="http://cybox.mitre.org/objects#FileObject"\
 xmlns:MemoryObj="http://cybox.mitre.org/objects#MemoryObject"\
 xmlns:NetworkRouteEntryObj="http://cybox.mitre.org/objects#NetworkRouteEntryObject"\
 xmlns:PortObj="http://cybox.mitre.org/objects#PortObject"\
 xmlns:ProcessObj="http://cybox.mitre.org/objects#ProcessObject"\
 xmlns:SystemObj="http://cybox.mitre.org/objects#SystemObject"\
 xmlns:UnixFileObj="http://cybox.mitre.org/objects#UnixFileObject"\
 xmlns:UserAccountObj="http://cybox.mitre.org/objects#UserAccountObject"\
 xmlns:VolumeObj="http://cybox.mitre.org/objects#VolumeObject"\
 xmlns:WinDriverObj="http://cybox.mitre.org/objects#WinDriverObject"\
 xmlns:WinEventLogObj="http://cybox.mitre.org/objects#WinEventLogObject"\
 xmlns:WinExecutableFileObj="http://cybox.mitre.org/objects#WinExecutableFileObject"\
 xmlns:WinFileObj="http://cybox.mitre.org/objects#WinFileObject"\
 xmlns:WinHandleObj="http://cybox.mitre.org/objects#WinHandleObject"\
 xmlns:WinKernelHookObj="http://cybox.mitre.org/objects#WinKernelHookObject"\
 xmlns:WinProcessObj="http://cybox.mitre.org/objects#WinProcessObject"\
 xmlns:WinRegistryKeyObj="http://cybox.mitre.org/objects#WinRegistryKeyObject"\
 xmlns:WinServiceObj="http://cybox.mitre.org/objects#WinServiceObject"\
 xmlns:WinSystemObj="http://cybox.mitre.org/objects#WinSystemObject"\
 xmlns:WinUserAccountObj="http://cybox.mitre.org/objects#WinUserAccountObject"\
 xmlns:WinVolumeObj="http://cybox.mitre.org/objects#WinVolumeObject"\
 xsi:schemaLocation="http://cybox.mitre.org/Common_v1 http://cybox.mitre.org/XMLSchema/cybox_common_types_v1.0(draft).xsd\
 http://stix.mitre.org http://stix.mitre.org/XMLSchema/STIX_v1.0_(Draft2).xsd\
 http://stix.mitre.org/Indicator http://stix.mitre.org/XMLSchema/STIX-Indicator_v1.1.xsd\
 http://cybox.mitre.org/objects#AccountObject http://cybox.mitre.org/XMLSchema/objects/Account/Account_Object_1.1.xsd\
 http://cybox.mitre.org/objects#AddressObject http://cybox.mitre.org/XMLSchema/objects/Address/Address_Object_1.1.xsd\
 http://cybox.mitre.org/objects#DiskObject http://cybox.mitre.org/XMLSchema/objects/Disk/Disk_Object_1.2.xsd\
 http://cybox.mitre.org/objects#DiskPartitionObject http://cybox.mitre.org/XMLSchema/objects/Disk_Partition/Disk_Partition_Object_1.2.xsd\
 http://cybox.mitre.org/objects#DNSRecordObject http://cybox.mitre.org/XMLSchema/objects/DNS_Record/DNS_Record_Object_1.0.xsd\
 http://cybox.mitre.org/objects#FileObject http://cybox.mitre.org/XMLSchema/objects/File/File_Object_1.2.xsd\
 http://cybox.mitre.org/objects#MemoryObject http://cybox.mitre.org/XMLSchema/objects/Memory/Memory_Object_1.1.xsd\
 http://cybox.mitre.org/objects#NetworkRouteEntryObject http://cybox.mitre.org/XMLSchema/objects/Network_Route_Entry/Network_Route_Entry_Object_1.0.xsd\
 http://cybox.mitre.org/objects#PortObject http://cybox.mitre.org/XMLSchema/objects/Port/Port_Object_1.2.xsd\
 http://cybox.mitre.org/objects#ProcessObject http://cybox.mitre.org/XMLSchema/objects/Process/Process_Object_1.2.xsd\
 http://cybox.mitre.org/objects#SystemObject http://cybox.mitre.org/XMLSchema/objects/System/System_Object_1.2.xsd\
 http://cybox.mitre.org/objects#UnixFileObject http://cybox.mitre.org/XMLSchema/objects/Unix_File/Unix_File_Object_1.2.xsd\
 http://cybox.mitre.org/objects#UserAccountObject http://cybox.mitre.org/XMLSchema/objects/User_Account/User_Account_Object_1.1.xsd\
 http://cybox.mitre.org/objects#VolumeObject http://cybox.mitre.org/XMLSchema/objects/Volume/Volume_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinDriverObject http://cybox.mitre.org/XMLSchema/objects/Win_Driver/Win_Driver_Object_1.1.xsd\
 http://cybox.mitre.org/objects#WinEventLogObject http://cybox.mitre.org/XMLSchema/objects/Win_Event_Log/Win_Event_Log_Object_1.1.xsd\
 http://cybox.mitre.org/objects#WinExecutableFileObject http://cybox.mitre.org/XMLSchema/objects/Win_Executable_File/Win_Executable_File_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinFileObject http://cybox.mitre.org/XMLSchema/objects/Win_File/Win_File_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinHandleObject http://cybox.mitre.org/XMLSchema/objects/Win_Handle/Win_Handle_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinKernelHookObject http://cybox.mitre.org/XMLSchema/objects/Win_Kernel_Hook/Win_Kernel_Hook_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinProcessObject http://cybox.mitre.org/XMLSchema/objects/Win_Process/Win_Process_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinRegistryKeyObject http://cybox.mitre.org/XMLSchema/objects/Win_Registry_Key/Win_Registry_Key_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinServiceObject http://cybox.mitre.org/XMLSchema/objects/Win_Service/Win_Service_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinServiceObject http://cybox.mitre.org/XMLSchema/objects/Win_System/Win_System_Object_1.1.xsd\
 http://cybox.mitre.org/objects#WinUserAccountObject http://cybox.mitre.org/XMLSchema/objects/Win_User_Account/Win_User_Account_Object_1.2.xsd\
 http://cybox.mitre.org/objects#WinVolumeObject http://cybox.mitre.org/XMLSchema/objects/Win_Volume/Win_Volume_Object_1.2.xsd\
 http://cybox.mitre.org/cybox_v1 http://cybox.mitre.org/XMLSchema/cybox_core_v1.0(draft).xsd"
 """
        namespacedef = "xmlns:" + prefix + "=\"" + namespace + "\" " + namespacedef
        package.export(open(outfilename, 'w'), 0, name_="STIX_Package", namespacedef_=namespacedef)
        if verbose_mode:
            for indicator_id in skipped_indicators:
                print "Indicator Item " + indicator_id + " Skipped; indicator type currently not supported"
        
    except Exception, err:
       print('\nError: %s\n' % str(err))
       if verbose_mode:
        traceback.print_exc()
                   
if __name__ == "__main__":
    main()