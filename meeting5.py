# -*- coding: utf-8 -*-
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
from recording.speech_t import speech_text
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

LabelBase.register(DEFAULT_FONT,'myfont.ttc')



# コマンドの定義
SET = 0
SUM = 1
WAV = 2
PLAY = 3
INPUT = 4
CON = 5
GIJI = 6

port = 9012
MSGLEN = 4096
#add = "18.179.223.246"
add = "18.179.223.246"
add = "ec2-18-179-223-246.ap-northeast-1.compute.amazonaws.com"


class AudioRecorder_Player:
    """ A Class For Audio """

    def __init__(self):
        self.audio_file = ""

        # 止める用のフラグ
        self.paused = threading.Event()
        self.CHUNK = 4094
        self.FORMAT = pyaudio.paInt16 # 16bit
        self.CHANNELS = 1             # monaural
        self.fs = 48000
        self.silent_th = 2
        self.threshold = 0.1
        self.rec_on = 0
        self.id = 0
        self.pac = bytes()
        self.sig_len = 2

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
            print(length)
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

        pac = PLAY.to_bytes(2, 'big')
        pac += wav_id.to_bytes(5,'big')
        r_packet =send_pac_recieve(pac)
        framerate = int.from_bytes(r_packet[0:4], 'big')
        samplewidth = int.from_bytes(r_packet[4:6], 'big')
        nchanneles = int.from_bytes(r_packet[6:8],'big')
        
        stream = pa.open(rate=framerate,
                channels=nchanneles,
                format=p.get_format_from_width(samplewidth),
                output=True,
                frames_per_buffer=self.CHUNK)
        data_list = [r_packet[8+idx:idx + self.CHUNK] for idx in range(0,len(r_packet[8:]), self.CHUNK)]
        for d in data_list:

            stream.write(d)

        stream.close()
        pa.terminate()
        self.PlayB.state = 'normal'
        
    def recieve_text(self,pac):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect((add, port))

            if pac:
                send_pac(client,pac)
            r_packet = bytes()
            while True:
                data = client.recv(4096)
                r_packet += data
                if not data:
                    break
        len_sum = 0
        print(len(r_packet))
        while True:
            wav_id =int.from_bytes(r_packet[len_sum:len_sum+5], 'big')
            type_ = int.from_bytes(r_packet[len_sum+5:len_sum+6], 'big')
            text_len = int.from_bytes(r_packet[len_sum+6:len_sum+8], 'big')
            
            text_r = r_packet[len_sum+8:len_sum+8+text_len]
            len_sum += len_sum+8+text_len
            text_r = text_r.decode('utf-8')
            textinput = Sentence(text=text_r)
            textinput.y += self.id
            text_play = FloatLayout()
            text_play.add_widget(textinput)
            pb = Play_Button()
            pb.wav_id = wav_id
            pb.y += self.id
            text_play.add_widget(pb)
            ts = Type_Spinner()
            ts.text = ts.values[type_]
            ts.y += self.id
            text_play.add_widget(ts)
            self.box.add_widget(text_play)
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
        self.pac += INPUT.to_bytes(2, 'big')
        self.pac += framerate.to_bytes(4,'big')
        self.pac += samplewidth.to_bytes(2,'big')
        self.pac += nchanneles.to_bytes(2,'big')
        self.pac += buf
        self.recieve_text(self.pac)
        
    def send_wav(self):
        # 送信は別のスレッドでする
        send_thread = threading.Thread(target = self.recieve_text,args=(self.pac,))
        send_thread.start()

                    
def recording(recorder,box):
    # 録音は別のスレッドでする
    audio_thread = threading.Thread(target=recorder.recordAudio,args=(box,))
    audio_thread.setDaemon(True)
    audio_thread.start()
    
def playing(player,wav_id):
    # 再生は別のスレッドでする
    audio_thread = threading.Thread(target=player.playAudio,args=(wav_id,))
    audio_thread.start()
    
    
def send_pac(client,q):
    print('connect to' , add, 'port:' ,port)
    packet = int(len(q)+4).to_bytes(4,'big')
    packet += q
    client.sendall(packet)
    print('sended')

def send_pac_recieve(pac):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((add, port))
        send_pac(client,pac)
        print('sended')
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
            
        #path = '/Users/shota/Documents/ginza/wikihow_japanese/data/output/test.jsonl'
        #test_data = pd.read_json(path, orient='records', lines=True)
        #a = test_data['src'][0].split('。')
        #a = [a2+'。' for a2 in a] 
        #a[random.randint(0,len(a)-1)]
        #box = self.parent.parent.children[1].children[0]
        #textinput = Sentence(text=a[random.randint(0,len(a)-1)])
        #textinput.y = self.id
        #text_play = FloatLayout()
        #text_play.add_widget(textinput)
        #pb = Play_Button()
        #pb.file_name = ''
        #pb.y = self.id
        #text_play.add_widget(pb)
        #box.add_widget(text_play)
        #self.id += 60
        #if self.id > self.parent.parent.children[1].children[0].height:
        #    self.parent.parent.children[1].children[0].height = self.id
            
class Sentence(TextInput):
    
   # def __init__(self,**kwargs):
    #    super().__init__(**kwargs)
     #   self.composition_string = ''
      #  self.tmp_text = ''
       # self.flag = False
        #self.ty = 0
        #self.tx = 0
        
    #def on_text_validate(instance):
     #   print('User pressed enter in', instance)
        
    #def on_text(self, value,a):
   #     if self.tmp_text:
     #       if len(self._text) > len(self.text):
      #          self._text = self.text
       #     else:
        #        self.text = self._text
    
   # def my_callback(self,_):
    #    self.text = self._text
     #   self.cursor = (self.tx,self.y)
      #  self.delete_selection(from_undo=False)
       # self.on_text_validate()
        #return False

    #def insert_text(self,substring, from_undo=False):
     #   s = substring.replace('\n','')
      #  if s:
       #     self._text += s
        #    self.tx = len(self._text)
        #else:
         #   self._text += '\n'
          #  self.ty += 1
           # self.tx = 0
        #Clock.schedule_interval(self.my_callback, 0.1)
        #return super(Sentence, self).insert_text(s, from_undo=from_undo)
        pass
class Type_Spinner(Spinner):
    
    pass

class Play_Button(ToggleButton):
    
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.CHUNK = 4096
        self.FORMAT = pyaudio.paInt16 # 16bit
        self.CHANNELS = 1             # monaural
        self.fs = 16000
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
            self.player.input_wav(fname)
            
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

        pac = GIJI.to_bytes(2, 'big')
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
            send_pac(client,pac)
        
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
                pac += SUM.to_bytes(2, 'big')
                tmp ="\n".join(tmp)
                pac += tmp.encode()
                r_packet = send_pac_recieve(pac)
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
        
    #スタートの処理
    pac = SET.to_bytes(2, 'big')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((add, port))
        send_pac(client,pac)
    app = Meeting4App()
    #app.dirnum = len([f.name for f in os.scandir('../Server/wav_file') if not f.name.startswith('.')])
    app.run()
