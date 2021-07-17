# -*- coding: utf-8 -*-from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.core.text import LabelBase,DEFAULT_FONT
from kivy.graphics import Color, Rectangle
from functools import partial
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import ObjectProperty
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.label import Label
from kivy.uix.slider import Slider
import os
import pyaudio
import numpy as np
import time
import wave
import socket
import multiprocessing 
import threading
import json
import pandas as pd
import random
from kivy.core.window import Window
import tkinter
from tkinter import ttk
from multiprocessing import Process
from kivy.properties import StringProperty
import math

LabelBase.register(DEFAULT_FONT,'myfont.ttc')



# コマンドの定義
SET = 0
SUM = 1
WAV = 2
PLAY = 3
INPUT = 4
CON = 5
GIJI = 6
BAFFA = 19200
port = 50005
MSGLEN = 8192
#add = "18.179.223.246"
add = "127.0.0.1"
#add = "ec2-18-179-223-246.ap-northeast-1.compute.amazonaws.com"


class AudioRecorder_Player:
    """ A Class For Audio """

    def __init__(self):
        self.audio_file = ""

        # 止める用のフラグ
        self.paused = threading.Event()
        self.CHUNK = 4410
        self.FORMAT = pyaudio.paInt16 # 16bit
        self.CHANNELS = 1             # monaural
        self.fs = 48000
        self.silent_th = 2
        self.threshold = 0.1
        self.rec_on = 0
        self.id = 0
        self.pac = bytes()
        self.sig_len = 2
        self.off_set = 0
        self.MSGlen = 0
        self.loading = 0
        self.seek = 0

    def recordAudio(self,box):
        stop_counter = 0
        length = 0 
        pa = pyaudio.PyAudio()
        self.box = box
        with open('Config.json') as f:
            df = json.load(f)
        mic_id = df['mic_id']
        stream = pa.open(rate=self.fs,
                channels=self.CHANNELS,
                format=self.FORMAT,
                input=True,
                input_device_index= mic_id,
                frames_per_buffer=self.CHUNK)
        
        while True:
            
            print('stand-by')
            # 音データの取得
            data = stream.read(self.CHUNK)
            # ndarrayに変換
            x = np.frombuffer(data, dtype="int16")
            x = x / 32768.0
            self.pac += WAV.to_bytes(2, 'big')
            self.pac += self.fs.to_bytes(4,'big')
            self.pac += int(2).to_bytes(2,'big')
            self.pac += self.CHANNELS.to_bytes(2,'big')
            # 閾値以上の場合はファイルに保存
            if x.max() > self.threshold:
                self.pac += data
                length += 1
                while True:
                    data = stream.read(self.CHUNK)
                    self.pac += data
                    length += 1
                    
                    x = np.frombuffer(data, dtype="int16") / 32768.0

                    if x.max() <= self.threshold:
                        stop_counter += 1
                        #設定秒間閾値を下回ったら一旦終了
                        if stop_counter >= (self.fs * self.silent_th / self.CHUNK):
                            stop_counter = 0
                        #設定秒間以上だったら送信
                            if length * self.CHUNK > self.fs * self.sig_len:   

                                self.send_wav()
                                
                            self.pac = bytes()
                            break
                    
            if self.paused.is_set():
                    # 再生を止める
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
                    # フラグを初期状態に
                    self.paused.clear()
                    break
                    
    def playAudio(self,wav_id):
        pa = pyaudio.PyAudio()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((add, port))
            pac = wav_id.to_bytes(5,'big')
            send_pac(client,PLAY,pac,None)
            r_cmd,MSG = recieve_pac(client)

            framerate = int.from_bytes(MSG[0:4], 'big')
            samplewidth = int.from_bytes(MSG[4:6], 'big')
            nchanneles = int.from_bytes(MSG[6:8],'big')
            nframes = int.from_bytes(MSG[8:],'big')
            #シークバー
            self.seek_bar = self.PlayB.parent.children[0]
            self.seek_bar.max = nframes
            self.seek_bar.min = 0
            self.seek_bar.value = 0
            self.off_set = 0
            self.loading = 0
            print("STREAMING")
            print("Channel num : ", nchanneles)
            print("Sample width : ", samplewidth)
            print("Sampling rate : ", framerate)
            self.data_array = bytearray(BAFFA)
            stream = pa.open(rate=framerate,
                    channels=nchanneles,
                    format=pa.get_format_from_width(samplewidth),
                    output=True,
                    frames_per_buffer=self.CHUNK)
            print('first CHUNK recieve')
            self.r_cmd,MSG = recieve_pac(client)
            self.data_array[:len(MSG)] = MSG 
            baffa_pos = 0       
            if self.r_cmd == 1:
               stream.write(bytes(self.data_array[:len(MSG)]))
            else:
	
               while self.off_set+BAFFA/2/samplewidth < nframes:
                  print('PLAY!')
                  DA = self.data_array[baffa_pos:baffa_pos+int(BAFFA/2)]
                  for i in range(0,int(BAFFA/2/self.CHUNK/2)):
                     stream.write(bytes(DA[i*self.CHUNK*2:(i+1)*self.CHUNK*2]))
                     self.off_set += self.CHUNK*2/samplewidth
                     self.seek_bar.value += self.CHUNK*2/samplewidth
                     if self.seek_bar.value != self.off_set:
                       self.off_set = self.seek_bar.value
                       self.seek = 1
                       print('break')
                       break
                  print('NEXT CHUNK recieve')
                  if self.loading == 0:
                     if self.seek == 1:
                        print('SEEK')
                        baffa_pos = 0
                        self.data_array = bytearray(BAFFA)
                        self.streaming(client,baffa_pos)

                     else:
                        streaming_thread(self,client,baffa_pos)

                        if baffa_pos == 0:
                           baffa_pos = int(BAFFA/2)
                        else:
                           baffa_pos = 0
                  else:
                     while self.loading == 1:
                        print('loading')
                        time.sleep(1)

        print('LAST CHUNK PLAY!!')
        stream.write(bytes(self.data_array[baffa_pos:baffa_pos+self.MSGlen]))
        self.seek_bar.value = nframes
        stream.close()
        pa.terminate()
        client.close()
        self.PlayB.state = 'normal'
        
    def recieve_text(self,type_ID,pac):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((add, port))

            if pac:
                if self.ProgressBar:
                    send_pac(client,type_ID,pac,self.ProgressBar)
                else:
                    send_pac(client,type_ID,pac,None)
            r_packet = bytes()
            while True:
                data = client.recv(4096)
                r_packet += data
                if not data:
                    break
        len_sum = 0
        while True:
            wav_id =int.from_bytes(r_packet[len_sum:len_sum+5], 'big')
            type_ = int.from_bytes(r_packet[len_sum+5:len_sum+6], 'big')
            text_len = int.from_bytes(r_packet[len_sum+6:len_sum+11], 'big')
            text_r = r_packet[len_sum+11:len_sum+11+text_len]
            len_sum += len_sum+11+text_len
            text_r = text_r.decode('utf-8')
            text_r = clean_text(text_r)
            S_Layout = Sentence_Layout()
            print('text_r',text_r)
            S_Layout.children[2].text = text_r
            S_Layout.y += self.id
            S_Layout.children[1].wav_id = wav_id
            self.box.add_widget(S_Layout)
            self.id += 100
            if self.id > self.box.height:
                self.box.height = self.id+30
                
            if len_sum >= len(r_packet):
                break
    def input_wav(self,fname):
        
        waveFile = wave.open(fname, 'r')
        buf = waveFile.readframes(-1)
        waveFile.close()
        # wavファイルの情報を取得
        # チャネル数：monoなら1, stereoなら2, 5.1chなら6(たぶん)
        nchanneles = waveFile.getnchannels()

        # 音声データ1サンプルあたりのバイト数。2なら2bytes(16bit), 3なら24bitなど
        samplewidth = waveFile.getsampwidth()

        # サンプリング周波数。普通のCDなら44.1k
        framerate = waveFile.getframerate()

        # 音声のデータ点の数
        nframes = waveFile.getnframes()

        print("Channel num : ", nchanneles)
        print("Sample width : ", samplewidth)
        print("Sampling rate : ", framerate)
        print("Frame num : ", nframes)
        self.pac = bytes()
        self.pac += framerate.to_bytes(4,'big')
        self.pac += samplewidth.to_bytes(2,'big')
        self.pac += nchanneles.to_bytes(2,'big')
        self.pac += buf
        self.recieve_text(INPUT,self.pac)

    def streaming(self,client,baffa_pos):
        self.loading = 1
        if self.seek == 1:
           header = 1
           print('SEEK OFF SET:',int(self.off_set))
           self.seek = 0
        else:
           header = 0
        q = int(self.seek_bar.value).to_bytes(MSGLEN-2,'big')
        send_pac(client,header,q,None)
        r_cmd,MSG = recieve_pac(client)
        self.r_cmd = r_cmd
        self.MSGlen = len(MSG)
        print('BAFFALEN',len(MSG))
        print('DOWNLOAD')
        self.data_array[baffa_pos:baffa_pos+len(MSG)] = MSG
        self.loading = 0
        
    def send_wav(self):
        # wavfile送信は別のスレッドでする
        send_thread = threading.Thread(target = self.recieve_text,args=(self.pac,))
        send_thread.start()

def streaming_thread(player,client,baffa_pos):

    audio_thread = threading.Thread(target=player.streaming,args=(client,baffa_pos))
    audio_thread.setDaemon(True)
    audio_thread.start()
          
def recording(recorder,box):
    # 録音は別のスレッドでする
    audio_thread = threading.Thread(target=recorder.recordAudio,args=(box,))
    audio_thread.setDaemon(True)
    audio_thread.start()
    
def playing(player,wav_id):
    # 再生は別のスレッドでする
    audio_thread = threading.Thread(target=player.playAudio,args=(wav_id,))
    audio_thread.start()
    
    
def send_pac(client,type_ID,q,ProgressBar):
    print('connect to' , add, 'port:' ,port)
    print(len(q))
    if ProgressBar:
       # ProgressBar.max = len(q)+(int(len(q)/MSGLEN)+1)*2
        ProgressBar.max = len(q)+2
        ProgressBar.value = 0
        
    offset = 0
    packet = bytearray(MSGLEN)
    packet[0:2] = type_ID.to_bytes(2,'big')
    packet[2:] = len(q).to_bytes(MSGLEN-2,'big')
    client.send(packet)

    while offset < len(q):
        packet[:] = q[offset:offset+MSGLEN]
        send_len = client.send(packet)
        offset += send_len
        if ProgressBar:
             ProgressBar.value = offset
    if ProgressBar:
        ProgressBar.value = len(q)
        ProgressBar.parent.popup_close()       
    print('sended')

def send_pac_recieve(type_ID,pac):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((add, port))
        send_pac(client,type_ID,pac,None)
        r_packet = bytes()
      
        while True:
            tmp = client.recv(4096)
            if tmp ==b'':
                raise RuntimeError("socket connection broken")
            r_packet += tmp
            if len(r_packet)>4:
                if len(r_packet) >= int.from_bytes(r_packet[0:4],'big'):
                    break
                    
    r_packet = r_packet[4:]
    
    return r_packet

def recieve_pac(client):

	MSGLEN = 8192
	cicle_t = 0
	data_len = 0
	offset = 0
	data_info = bytes()
	while data_len < MSGLEN:
		tmp = client.recv(MSGLEN)
		data_info += tmp
		data_len = len(data_info)
	r_cmd = int.from_bytes(data_info[0:2], 'big')
	data_len = int.from_bytes(data_info[2:MSGLEN],'big')
	MSG = bytearray(data_len)
	offset += len(data_info)-MSGLEN
	MSG[:offset]=data_info[MSGLEN:]
	while offset < data_len:
		start_t = time.time()
		tmp = client.recv(MSGLEN)
		recv_t = time.time()
		MSG[offset:offset+len(tmp)] = tmp
		offset += len(tmp)

	return r_cmd, MSG
def clean_text(text):
    ngw= ['',' ','　']
    text = text.split('\n')
    text = [t for t in text if t not in ngw ]
    tc = []
    for t in text:
        tmp = t.split('。')
        
        for t in tmp:
            if t not in ngw:
                tc.append(t)
                
    tc = '\n'.join(tc)            
    
    return tc

class REC_Button(ToggleButton):
    
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.CHUNK = 4094
        self.FORMAT = pyaudio.paInt16 # 16bit
        self.CHANNELS = 1             # monaural
        self.fs = 16000
        self.silent_th = 2
        self.threshold = 0.1
        self.rec_on = 0
        self.id = 0
        self.pac = bytes()
        self.sig_len = 2
        self.recorder = AudioRecorder_Player()
        self.id = 0

    def on_press(self):
        
        if self.state == 'down':
            recording(self.recorder,self.parent.parent.children[1].children[0])
            self.text = '録音中'
        else:
            self.recorder.paused.set()
            self.text = '録音開始'

class Sentence(TextInput):
    
        pass
class Type_Spinner(Spinner):
    
    pass

class Play_Button(ToggleButton):
    
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.player = AudioRecorder_Player()

    def on_press(self):
        pass
        
    def on_release(self):
        if self.state == 'normal':
            self.state = 'down'
        else:
            self.player.PlayB = self
            playing(self.player,self.wav_id)
        
class SettingMenu(BoxLayout):
    popup_close = ObjectProperty(None)
    
class InputMenu(BoxLayout):
    popup_close = ObjectProperty(None)

    
    def wav_send(self):
        print(self.children[1].selection)
        if self.children[1].selection:
            fname = self.children[1].selection[0]
            self.player.ProgressBar = self.children[2]
            #アップロードは別のスレッドでする
            audio_thread = threading.Thread(target=self.player.input_wav,args=(fname,))
            audio_thread.start()
            
            
    def set_player(self,player):
        self.player = player
        
            
class SummaryMenu(BoxLayout):
    popup_close = ObjectProperty(None)

    def text_output(self):
        with open('text0.json') as f:
            df = json.load(f)
        if 'texts' in df:
            return str(df['texts'])
        else:
            return 

    def summary_output(self):
        with open('text0.json') as f:
            df = json.load(f)
        if 'summary' in df:
            return str(df['summary'])
        else:
            return
        
    def task_output(self):
        with open('text0.json') as f:
            df = json.load(f)
        if 'task' in df:
            return str(df['task'])
        else:
            return
        
    def send_giji(self):

        #本文
        if self.children[1].children[4].text:
            t = self.children[1].children[4].text.encode()
            pac += int(len(t)).to_bytes(4,'big')
            pac += t
        else:
            pac += int(0).to_bytes(4,'big')
        #要約
        if self.children[1].children[2].text:
            t = self.children[1].children[2].text.encode()
            pac += int(len(t)).to_bytes(4,'big')
            pac += t
        else:
            pac += int(0).to_bytes(4,'big')
        #タスク
        if self.children[1].children[0].text:
            t = self.children[1].children[2].text.encode()
            pac += int(len(t)).to_bytes(4,'big')
            pac += t
        else:
            pac += int(0).to_bytes(4,'big')
          
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((add, port))
            send_pac(client,GIJI,pac,None)
        
        return
        
class TestInput(TextInput):
    
    pass
    
class input_spinner(Spinner):
    def __init__(self,**kwargs):
        self.set_miclist()
        super().__init__(**kwargs)
        
    
    def set_miclist(self):
        p = pyaudio.PyAudio()
        mic_list =  [x for x in range(0,p.get_device_count())]
        name_list = []
        for index in range(0, p.get_device_count()):
            if p. get_device_info_by_index(index)['maxInputChannels'] > 0:
                mic_list[index] = p. get_device_info_by_index(index)['name']
                name_list.append(p. get_device_info_by_index(index)['name'])
        self.values = name_list
        with open('Config.json') as f:
            df = json.load(f)
            
        self.text = mic_list[df['mic_id']]
 
        self.mic_list = mic_list
            
    def on_text(self,text,a):
        with open('Config.json') as f:
            df = json.load(f)
            
        df['mic_id']= [i for i,k in enumerate(self.mic_list) if k == self.text][0]
        
        with open('config.json', 'w') as f:
            json.dump(df, f, ensure_ascii=False)

class output_spinner(Spinner):
    def __init__(self,**kwargs):
        self.set_splist()
        super().__init__(**kwargs)
        
    
    def set_splist(self):
        p = pyaudio.PyAudio()
        sp_list =  [x for x in range(0,p.get_device_count())]
        name_list = []
        for index in range(0, p.get_device_count()):
            if p. get_device_info_by_index(index)['maxOutputChannels'] > 0:
                sp_list[index] = p. get_device_info_by_index(index)['name']
                name_list.append(p. get_device_info_by_index(index)['name'])
        self.values = name_list
        with open('Config.json') as f:
            df = json.load(f)
            
        self.text = sp_list[df['sp_id']]
 
        self.sp_list = sp_list
            
    def on_text(self,text,a):
        with open('Config.json') as f:
            df = json.load(f)
            
        df['sp_id']= [i for i,k in enumerate(self.sp_list) if k == self.text][0]
        
        with open('config.json', 'w') as f:
            json.dump(df, f, ensure_ascii=False)
        
class Setting_Button(Button):
    
    def on_press(self):
        content = SettingMenu(popup_close=self.popup_close)
        self.popup = Popup(title='設定画面', content=content, size_hint=(1, 1), auto_dismiss=False)
        self.popup.open()
        
    def popup_close(self):
        self.popup.dismiss()
        
class Summary_Button(Button):
    
    def on_press(self):
        result = ''
        suma = ''
        task = ''
        imp = ''
        if self.parent.parent.children[1].children[0].children:
            tmp = [clean_text(a.children[2].text) for a in reversed(self.parent.parent.children[1].children[0].children) if a.children[2].text != '']
            task = "\n".join([a.children[2].text for a in reversed(self.parent.parent.children[1].children[0].children) if a.children[0].text == 'タスク'])
            
            result = "\n".join(tmp)    
            if len(tmp) > 1:
                pac = bytes()
                tmp ="\n".join(tmp)
                pac += tmp.encode()
                r_packet = send_pac_recieve(SUM,pac)
                suma = r_packet.decode()
                suma = suma.split('。') 
                suma = [a+ '。' for a in suma]
                suma = suma[:-1]
            imp = [a.children[2].text for a in reversed(self.parent.parent.children[1].children[0].children) if a.children[0].text == '重要' and a.children[2].text not in suma]
            
            imp = "\n".join(imp)+ "\n".join(suma)

        with open('text0.json') as f:
            df = json.load(f)
        df['texts']=result
        df['summary'] = imp
        df['task'] = task
        with open('text0.json', 'w') as f:
            json.dump(df, f, ensure_ascii=False)
            
        content = SummaryMenu(popup_close=self.popup_close)
        self.popup = Popup(title='議事録', content=content, size_hint=(1, 1), auto_dismiss=False)
        self.popup.open()
    
    
    def popup_close(self):
        self.popup.dismiss()

class Input_Button(Button):
    
    def on_press(self):
        audio_player = AudioRecorder_Player()
        audio_player.box = self.parent.parent.children[1].children[0]
        content = InputMenu(popup_close=self.popup_close,)
        content.set_player(audio_player)
        self.popup = Popup(title='ファイル選択', content=content, size_hint=(1, 1), auto_dismiss=False)
        self.popup.open()
        
    def popup_close(self):
        self.popup.dismiss()
        
   
class Text_Layout(FloatLayout):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
            
class Sentence_Layout(BoxLayout):
    pass
class Seek_Bar(Slider):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.touch_sl = False
    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self.touch_sl == False:
          self.touch_sl = True 
class Button_Layout(BoxLayout):
    pass

    
class MyRoot(BoxLayout):
    orientation='vertical'  
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.rec_on = 0


class Meeting4App(App):
    
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.id = 0
            
    def add_text(self,box,a):
        text,self.dirnum = speech_text(self.dirnum)
        
        def on_enter(ti):
            print("on_enter[%s]" % (ti.text))
            print(ti.cursor[0])

        if text:

            for t in text:
                textinput = Sentence(text=str(t))
                textinput.y = self.id
                textinput.bind(on_text_validate=on_enter)
                text_play = FloatLayout()
                text_play.add_widget(textinput)
                pb = Play_Button()
                pb.file_name = text[t][1]
                pb.y = self.id
                text_play.add_widget(pb)
                box.add_widget(text_play)
                self.id += 60

                
    def build(self):
        
        root = MyRoot() 

        #Clock.schedule_interval(partial(self.add_text,root.children[1].children[0]), 1.0 / 60.0)

        return root
   

if __name__ == '__main__':
    
    #デバイス確認の処理
    p = pyaudio.PyAudio()
    mic_ids = []
    sp_ids = []
    for index in range(0, p.get_device_count()):
        if p. get_device_info_by_index(index)['maxInputChannels'] > 0:
            mic_ids.append(index)
        if p. get_device_info_by_index(index)['maxOutputChannels'] > 0:
            sp_ids.append(index)
            
    with open('Config.json') as f:
        df = json.load(f)
    if df['mic_id'] not in mic_ids:
        df['mic_id'] = mic_ids[0]  
            
    if df['sp_id'] not in sp_ids:
        df['sp_id'] = sp_ids[0] 

    with open('Config.json', 'w') as f:
        json.dump(df, f, ensure_ascii=False)  
    pac = bytes(1)      
    #スタートの処理
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((add, port))
        send_pac(client,SET,pac,None)
    app = Meeting4App()
    #app.dirnum = len([f.name for f in os.scandir('../Server/wav_file') if not f.name.startswith('.')])
    app.run()

