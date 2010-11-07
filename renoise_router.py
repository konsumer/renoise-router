#!/usr/bin/env python

"""
This will wait for incoming events, and resend them as OSC to Renoise
Requires python-pygame python-yaml 

and

https://trac.v2.nl/wiki/pyOSC

"""

#TODO: device['interfaces'] needs to be fixed. should be a dict, keyed to system ID.

import os, sys
import pygame
from pygame.locals import *
import pygame.midi
import time
import OSC

# used for debugging...
import inspect
def whoami():
    return inspect.stack()[1][3]

# they are Userevents, with a type id of 34.
MIDI_EVENT=34

MIDI_NOTEOFF=0x80
MIDI_NOTEON=0x90
MIDI_POLYPRESSURE=0xA0
MIDI_CONTROLCHANGE=0xB0
MIDI_PROGRAMCHANGE=0xC0
MIDI_CHANNELPRESSURE=0xD0
MIDI_PITCHCHANGE=0xE0

MIDI_SYSEX=0xF0
MIDI_TIMECODE=0xF1
MIDI_SONGPOSITION=0xF2
MIDI_SONGSELECT=0xF3
MIDI_USER1=0xF4
MIDI_USER2=0xF5
MIDI_TUNEERQUEST=0xF6
MIDI_EOX=0xF7




class RenoiseDeviceRouter:
    def __init__(self, device_map={}, renoise_host='localhost', renoise_port=8000):
        self.renoise_host = renoise_host
        self.renoise_port = renoise_port
        
        os.environ["SDL_VIDEO_CENTERED"] = "1"
        
        pygame.init()
        pygame.fastevent.init()
        pygame.midi.init()
        
        self.width = 800
        self.height = 80
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Renoise Device Server")
        
        self.font = pygame.font.Font(pygame.font.get_default_font(), 15)
        self.background = pygame.Surface(self.screen.get_size())
        self.background = self.background.convert()
        self.background.fill((0, 0, 0))
        self.screen.blit(self.background, (0, 0))
        
        self.last_osc = "None"
        
        self.device_map = {'midi':{}, 'joystick':{}}
        self.devices = {'midi':{}, 'joystick':{}}
        
        self.client = OSC.OSCClient()
        self.client.connect( (self.renoise_host, self.renoise_port) )
        
        # init devices, and put in devices storing system-key in device_info
        for device_type in device_map:
            for device_info in device_map[device_type]:
                if device_type == "midi":
                    # find the device in system list, add to map and device list
                    for i in range(pygame.midi.get_count()):
                        info = pygame.midi.get_device_info(i)
                        if info[3] == 0 and device_info['name'] == info[1]: # input device & name matches
                            self.devices[device_type][i] = pygame.midi.Input(i)
                            self.device_map[device_type][i] = device_info
                            self.device_map[device_type][i]['device_id'] = i
                            break
                elif device_type == "joystick":
                    # find the device in system list, add to map and device list
                    for i in range(pygame.joystick.get_count()):
                        j=pygame.joystick.Joystick(i)
                        if j.get_name() == device_info['name']: # name matches
                            self.devices[device_type][i] = j
                            self.devices[device_type][i].init()
                            self.device_map[device_type][i] = device_info
                            self.device_map[device_type][i]['device_id'] = i
                            break
                    
                # here keyboards, mice, and anything else you want could be added, similar to midi & joystick.
                # just iterate through list, then add to devices & device_map, keyed by id that event sends as device ID
        
        # give you info about your devices        
        print "Available devices:"
        h = "System".center(15) + "|" + "Name".center(50) + "|" + "Enabled".center(10)
        print "-" * len(h)
        print h
        print "-" * len(h)
        
        for device_id in range(pygame.midi.get_count()):
            device_info, interface = self.get_device("midi", device_id)
            real_info = pygame.midi.get_device_info(device_id)
            if real_info[3] == 0: # input device
                if interface:
                    print real_info[0].center(15) + "|" + real_info[1].center(50) + "|" + "[*]".center(10)
                else:
                    print real_info[0].center(15) + "|" + real_info[1].center(50) + "|" + "[ ]".center(10)
        
        print "-" * len(h)
        
        for device_id in range(pygame.joystick.get_count()):
            device_info, interface = self.get_device("joystick", device_id)
            real_info=('SDL joystick', j.get_name())
            if interface:
                print real_info[0].center(15) + "|" + real_info[1].center(50) + "|" + "[*]".center(10)
            else:
                print real_info[0].center(15) + "|" + real_info[1].center(50) + "|" + "[ ]".center(10)
        print "-" * len(h)
    
    
    def get_device(self, device_type, device_id):
        """ if device_id is a string, find by name or id, if it's an int, find by device_id, returns (device_info, interface) or False, if not found """
        try:
            if type(device_id) == type(""):
                for i in self.device_map[device_type]:
                    if self.device_map[device_type][i]['name'] == device_id or self.device_map[device_type][i]['id'] == device_id:
                        return self.device_map[device_type][i], self.devices[device_type][i]
            elif type(device_id) == type(1):
                return self.device_map[device_type][device_id], self.devices[device_type][device_id]
        except KeyError:
            return None, None
    
    def osc(self, address, *data):
        """ simple wrapper around sending osc messages to Renoise OSC """
        msg = OSC.OSCMessage()
        msg.setAddress('/renoise' + address)
        for d in data:
            msg.append(d)
        self.last_osc=msg
	try:        
		self.client.send(msg)
	except OSC.OSCClientError,err:
		print err
        
    def send_midi_control(self, channel, control, val):
        """ wrapper to make code easier to read... """
        msg = int(val) << 16 | control << 8 | 0xB0+channel
        print "control %d %d %d" % (channel, control, val)
        self.osc('/trigger/midi', msg)
    
    def scale_num(self, a, aMin=0.000, aMax=1.000, omin=0.000, omax=127.000):
        """ scale a number into the range of midi. there must be a stdlib/builtin function for this... """
        val = (a / ((aMax - aMin) / (omax - omin))) + omin
        print "scale_name", a, aMin, aMax, omin, omax, val
        return val
    
    def main_loop(self):
        while True:
            # pump midi events into event queue
            for device_id in self.devices["midi"]:
                if self.devices["midi"][device_id].poll():
                    midi_events = self.devices["midi"][device_id].read(10)
                    midi_evs = pygame.midi.midis2events(midi_events, device_id)
                    for m_e in midi_evs:
                        pygame.fastevent.post( m_e )
            
            # these are used for display
            device_type = 'none'
            device_id = None
            trigger="None"
            data = {}
            event = None
            trigger = "None"
            device_name="None"
            do_event = False;
            
            for event in pygame.fastevent.get():
                if event.type == pygame.QUIT:
                    self.client.close()
                    del(self.client)
                    for i in self.devices['midi']:
                        self.devices['midi'][i].close()
                        del(self.devices['midi'][i])
                    pygame.quit()
                    sys.exit(0)
                elif event.type == MIDI_EVENT and event.status in self.device_map["midi"][event.vice_id]['events'].keys():
                    device_id = event.vice_id
                    do_event = True
                    device_type = "midi"
                    device_name = self.device_map["midi"][device_id]['name']
                    trigger = self.device_map["midi"][device_id]['events'][event.status]
                    
                    #XXX I'm bad with binary. is there a better way?
                    self.device_map["midi"][device_id]["channel_command"] = eval('0x'+hex(event.status)[2]+'0')
                    self.device_map["midi"][device_id]["channel"] = event.status - self.device_map["midi"][device_id]["channel_command"]
                    
                    self.trigger_handler(event, "midi", device_id, self.device_map["midi"][device_id]['events'][event.status])
                else:
                    for device_type in self.device_map:
                        for device_id in self.device_map[device_type]:
                            # add more here, if you have other specialized handlers, and add above, like midi
                            if device_type not in ("midi"):
                                if event.type in self.device_map[device_type][device_id]['events'].keys():
                                    do_event = True
                                    device_name = self.device_map[device_type][device_id]['name']
                                    trigger = self.device_map[device_type][device_id]['events'][event.type]
                                    self.trigger_handler(event, device_type, device_id, trigger)
                                    break
            
            if do_event:
                self.screen.blit(self.background, (0, 0))
                
                # display the last event
                self.screen.blit( self.font.render("Last Event: %s" % device_name, 1, (255, 255, 255)), (2,2))
                self.screen.blit( self.font.render("Type: %s" % trigger.title().replace('_', ' '), 1, (200, 200, 200)), (5,22))
                self.screen.blit( self.font.render("Data: %s" % str(event), 1, (200, 200, 200)), (5,40))
                self.screen.blit( self.font.render("OSC: %s" % self.last_osc, 1, (200, 200, 200)), (5,58))
                
                pygame.display.update()
            
            time.sleep(0.01)
    
    
    def trigger_handler(self, event, device_type, device_id, trigger):
        """ Event handler routes to methods available in this class, based on type and mapping. """
        # print "trigger %s_%s(%s, %s)" % (device_type, trigger, event, device_id)
        try:
            getattr(self, "%s_%s" % (device_type, trigger) )(event, device_id)
        except AttributeError, err:
            print err
    
    # some decent default handlers
    
    def midi_note_on(self, event, device_id):
        try:
            instrument = self.device_map["midi"][device_id]["instrument"] + self.device_map["midi"][device_id]["channel"]
            track = self.device_map["midi"][device_id]["track"] + self.device_map["midi"][device_id]["channel"]
            self.osc('/trigger/note_on', instrument, track, event.data1, event.data2)
        except KeyError:
            pass
    
    def midi_note_off(self, event, device_id):
        try:
            instrument = self.device_map["midi"][device_id]["instrument"] + self.device_map["midi"][device_id]["channel"]
            track = self.device_map["midi"][device_id]["track"] + self.device_map["midi"][device_id]["channel"]
            self.osc('/trigger/note_off', instrument, track, event.data1)
        except KeyError:
            pass
    
    def midi_control(self, event, device_id):
        self.send_midi_control(device_id,  event.data1, event.data2)
    
    def midi_pitch(self, event, device_id):
        try:
            self.send_midi_control(device_id,  self.device_map["midi"][device_id]["pitch_control"], event.data2)
        except KeyError:
            pass
    
    def joystick_axis_motion(self, event, device_id):
        # send as a control, over midi
        try:
            i = self.device_map["joystick"][device_id]['axis_controls'][event.axis]
            channel = self.device_map["joystick"][device_id]['control_channel']
            control = i['control']
            val = self.scale_num(event.value, i['low'], i['high'])
            self.send_midi_control(channel, control, val)
        except KeyError:
            pass
        
    
    def joystick_hat_motion(self, event, device_id):
        try:
            i = self.device_map["joystick"][device_id]['hat_controls'][event.axis]
            channel = self.device_map["joystick"][device_id]['control_channel']
            control = i['control']
            val = self.scale_num(event.axis, i['low'], i['high'])
            self.send_midi_control(channel, control, val)
        except KeyError:
            pass
            
    
    def joystick_button_down(self, event, device_id):
        try:
            control = self.device_map["joystick"][device_id]['button_controls'][event.button]
            channel = self.device_map["joystick"][device_id]['control_channel']
            val = 127
            self.send_midi_control(channel, control, val)
        except KeyError:
            pass
        
    
    def joystick_button_up(self, event, device_id):
        try:
            control = self.device_map["joystick"][device_id]['button_controls'][event.button]
            channel = self.device_map["joystick"][device_id]['control_channel']
            val = 0
            self.send_midi_control(channel, control, val)
        except KeyError:
            pass

class ForkbombRenoiseDeviceRouter(RenoiseDeviceRouter):
    """
    Specialized handlers for my setup.
    
    Guitar works like this:
    strummer is selector for note arrays (3 of them) buttons map to notes
    all notes die when you change strum direction
    
    volume switch is instrument selector
    
    whammy & buttons are standard midi controls
    
    transport buttons on oxygen25 control current song, which is pulled from a dir named "set_list" in current dir.
    
    """
    def __init__(self, device_map={}, renoise_host='localhost', renoise_port=8000):
        RenoiseDeviceRouter.__init__(self, device_map, renoise_host, renoise_port)
        
        # setup some defaults for all my joystics
        for device_id in self.device_map["joystick"]:
            self.device_map["joystick"][device_id]['current_instrument']=0
            self.device_map["joystick"][device_id]['current_guitar_strum']=1
        
        # setup the tracks to be scrolled through in setlist
        self.tracks = []
        for dirname, dirnames, filenames in os.walk('set_list'):
            for filename in filenames:
                self.tracks.append(os.path.join(dirname, filename))
        
	    self.current_track = 0
        self.tracks.sort()
            
        # load first track
        # self.osc('/evaluate', 'renoise.app():load_song("%s")' % self.tracks[self.current_track])
	 
    
    def joystick_hat_motion_guitar(self, event, device_id): # strum + directional
        """ Play current notes """
        if event.value[0] == 0: # handle strum
            self.device_map["joystick"][device_id]['current_guitar_strum'] = event.value[1] + 1
            track =  self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['track']
            instrument = self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['instrument']
            # all others go away...
            for strum in range(3):
                if strum is not self.device_map["joystick"][device_id]['current_guitar_strum']:
                    for note in self.device_map["joystick"][device_id]['guitar_note_map'][strum]:
                        self.osc('/trigger/note_off', instrument, track, note)
        else: # trigger controls
            self.joystick_hat_motion(event, device_id)
    
    def joystick_axis_motion_guitar(self, event, device_id):
        """ whammi + channel selector """
        if event.axis == 2:
            if event.value == -0.80318613238929415:
                self.device_map["joystick"][device_id]['current_instrument'] =  0
            elif event.value == -0.40159306619464707:
                self.device_map["joystick"][device_id]['current_instrument'] =  1
            elif event.value == 0.0:
                self.device_map["joystick"][device_id]['current_instrument'] =  2
            elif event.value == 0.40156254768517108:
                self.device_map["joystick"][device_id]['current_instrument'] =  3
            elif event.value == 0.80315561387981815:
                self.device_map["joystick"][device_id]['current_instrument'] =  4
            print "Instrument changed to %d" % self.device_map["joystick"][device_id]['current_instrument']
        else:
            self.joystick_axis_motion(event, device_id)
        
    def midi_transport_control(self, event, device_id): # oxygen's transport controls
        """ track up/down scrolls through tracks """     
        if event.data1 == 110:# track <
            if event.data2==127:
                if self.current_track == 0:
                    self.current_track = len(self.tracks)-1
                else:
                    self.current_track = self.current_track -1
                self.osc('/evaluate', 'renoise.app():load_song("%s")' % os.path.realpath(self.tracks[self.current_track]))
        elif event.data1 == 111:# track >
            if event.data2==127:          
                if self.current_track == len(self.tracks)-1:
                    self.current_track = 0
                else:
                    self.current_track = self.current_track +1
                self.osc('/evaluate', 'renoise.app():load_song("%s")' % os.path.realpath(self.tracks[self.current_track]))
        else: # send on to regular control message router
            self.midi_control(event, device_id)
            
    
    def joystick_button_down_guitar(self, event, device_id):
        """ update current buttons """
        if event.button < 5:
            strum = self.device_map["joystick"][device_id]['current_guitar_strum']
            note = self.device_map["joystick"][device_id]['guitar_note_map'][strum][event.button]
            track =  self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['track']
            instrument = self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['instrument']
            self.osc('/trigger/note_on', instrument, track, note, 100)
        else:
            self.joystick_button_down(event, device_id)
            
    
    def joystick_button_up_guitar(self, event, device_id):
        """ update current buttons, trigger noteoff """
        if event.button < 5:
            track =  self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['track']
            instrument = self.device_map["joystick"][device_id]['current_instrument']+self.device_map["joystick"][device_id]['instrument']
            
            # turn off current strum, others are turned of if strum changes.
            strum = self.device_map["joystick"][device_id]['current_guitar_strum']
            note = self.device_map["joystick"][device_id]['guitar_note_map'][strum][event.button]
            self.osc('/trigger/note_off', instrument, track, note)
        else:
            self.joystick_button_up(event, device_id)
            
                


def parse_yaml(directory=None):
    """ parses my custom YML formatted config file, and returns (device_map, host, port) """
    import yaml
    
    if directory == None:
        directory = os.path.join(os.path.dirname(__file__), 'devices')
    
    dev_map = {}
    
    for device_type in os.listdir(directory):
        dev_map[device_type]=[]
        print device_type
        for fname in os.listdir(os.path.join(directory,device_type)):
            device_id = fname.split('.')[0]
            print "  ", device_id
            f = open(os.path.join(directory,device_type, fname),"r")
            d = yaml.load(f)
            d['id']=device_id
            dev_map[device_type].append(d)
            f.close()
    
    print ""
    print dev_map
    

    return dev_map, "localhost", 8000


if __name__ == "__main__":
    dev_map, host, port = parse_yaml()
    window = ForkbombRenoiseDeviceRouter(device_map=dev_map, renoise_host=host, renoise_port=port)
    window.main_loop()


