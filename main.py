import requests as r
import random
from PIL import Image, ImageFilter
import io
import time
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import datetime
import base64
import cv2
base_uri = "http://IP:PORT/image.jpg?rand="
cap = cv2.VideoCapture("http://IP:PORT?frame_count=1000000000")
chars = [chr(i) for i in range(97,123)]
NUM_OF_IMGS = 10
MAXIMAGEINLOOP = 5
DIFFERENCE_RANGE = 22
RESIZER = 5
is_conntected = False
def get_img():
    a = r.get(base_uri+"".join(random.choices(chars, k=10)))
    return a.content

def reduce_img(img):
    global RESIZER
    image_data = img
    image = Image.open(io.BytesIO(image_data))
    image = image.resize((int(image.size[0]/RESIZER),int(image.size[1]/RESIZER)))
    image = image.convert("RGB")
    return image

def get_bank_of_images(n:int):
    bank_of_images = []
    for i in range(n):
        bank_of_images.append({})
        bank_of_images[i]["img"]=reduce_img(get_img())
        bank_of_images[i]["size"] = bank_of_images[i]["img"].size 
        emit("progress" , {"data":"getting images","progress":i+1,"total":n},json=True)
        print(f"[+] Got image {i+1}/{n}")
        send_img_temp(bank_of_images[i]["img"],"actual image","actual")
    return bank_of_images

def get_diff(px:tuple,px2:tuple):
    diff_score = 0
    for i in range(len(px)):
        diff_score += abs(px[i]-px2[i])
    return diff_score

def percent_to_pixel(force:int):
    """a function to make a gradient from red to white"""
    if force==0:return (0,0,0,255)
    else: return (0, 0, 0, 0)


def send_img_temp(img,message,id):
    buff = io.BytesIO()
    img.save(buff, format="PNG")
    raw = base64.b64encode(buff.getvalue())
    return emit("image" , {"raw":raw.decode("utf-8"),"timestamp":time.time(),"plus":{"message":message,"id":id}},json=True)

errors_stream = 0

def loop_mode(reset_heat=False,stream_cam=False):
    global cap  #for streams
    global RESIZER
    global is_conntected
    global errors_stream
    print("[+] Starting loop mode")
    log_n_emit("getting first image..")
    if stream_cam:
        _, frame = cap.read()
        try:
            cv2_im = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
            first_img = Image.fromarray(cv2_im)
            first_img = first_img.resize((int(first_img.size[0]/RESIZER),int(first_img.size[1]/RESIZER)))
        except Exception as e:
            log_n_emit("Error while getting first image")
            errors_stream += 1
            if errors_stream >= 5:
                errors_stream = 0
                return log_n_emit("Too many errors, stopping loop mode")
            return loop_mode(reset_heat,stream_cam)
    else:
        first_img = reduce_img(get_img())
    width ,height = first_img.size
    firstmap = first_img.getdata()
    accumulated_images = []
    heatmap = [0 for i in range(len(firstmap))]
    while True:
        if reset_heat:
            heatmap = [0 for i in range(len(firstmap))]
        if stream_cam:
            _, frame = cap.read()
            try:
                cv2_im = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2_im)
                img = img.resize((width,height))
            except Exception as e:
                log_n_emit("Error while getting first image")
                errors_stream += 1
                if errors_stream >= 5:
                    errors_stream = 0
                    return log_n_emit("Too many errors, stopping loop mode")
                return loop_mode(reset_heat,stream_cam)
        else:
            img = reduce_img(get_img())
        accumulated_images.append({"imgdata":img.getdata(),"life":MAXIMAGEINLOOP})
        for i in range(len(accumulated_images)):
            if i>=len(accumulated_images):break
            #print(str(i)+"-life: ",accumulated_images[i]["life"])
            accumulated_images[i]["life"] -= 1
            if accumulated_images[i]["life"] <= 0:
                accumulated_images.pop(i)
        send_img_temp(img,"actual image treating","actual")
        for i in range(len(accumulated_images)):
            for j in range(len(accumulated_images[i]["imgdata"])):
                if j>=len(firstmap) or j>= len(accumulated_images[i]["imgdata"]):return loop_mode(reset_heat,stream_cam)
                px = accumulated_images[i]["imgdata"][j]
                diff_score = get_diff(px,firstmap[j])
                if diff_score >= DIFFERENCE_RANGE:
                    heatmap[j] += int(diff_score*(1+(accumulated_images[i]["life"]*0.1)))#the fartest is an image, the less we add to heatmap
        #convert the heatmap to a pixel value
        heatmap_pixel = [percent_to_pixel(i) for i in heatmap]
        #create the image
        new_image = Image.new("RGBA",(width,height))
        new_image.putdata(heatmap_pixel)
        #new_image = new_image.filter(ImageFilter.GaussianBlur(radius=5)) #blur the image to make it more readable
        send_img_temp(new_image,"actual heatmap","heatmap")
        log_n_emit("Looping...")
        if not is_conntected:
            print("[-] Stopping loop mode")
            return

def log_n_emit(msg):
    print(f"[{datetime.datetime.now()}] {msg}")
    return emit("progress" , {"data":msg},json=True)

def main():
    log_n_emit("getting images")
    bank_of_images = get_bank_of_images(NUM_OF_IMGS)
    log_n_emit("treating img...")
    width ,height = bank_of_images[0]["size"]
    firstmap = bank_of_images[0]["img"].getdata()
    heatmap = [0 for i in range(len(firstmap))]
    for i in range(1,len(bank_of_images)):
        dataimg = bank_of_images[i]["img"].getdata()
        for j in range(len(dataimg)):
            px = dataimg[j]
            diff_score = get_diff(px,firstmap[j])
            if diff_score > 10*(NUM_OF_IMGS/4):
                heatmap[j] += 25
    #convert the heatmap to a pixel value
    heatmap = [percent_to_pixel(i) for i in heatmap]
    #create the image
    new_image = Image.new("RGB",(width,height))
    new_image.putdata(heatmap)
    #new_image =  new_image.filter(ImageFilter.GaussianBlur(radius=3)) 
    send_img_temp(new_image,"heatmap","heatmap")
    new_image.save("heatmap.png")
    log_n_emit("All done !")


app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('./index.html')


@socketio.on('connect')
def test_connect(auth):
    global is_conntected
    print("[+] Client connected",auth)
    emit("after connect",{'data': 'Connected'}, json=True)
    is_conntected = True

@socketio.on('disconnect')
def test_disconnect():
    global is_conntected
    global errors_stream
    print('[-] Client disconnected')
    is_conntected = False
    errors_stream = 0

@socketio.on('start')
def handle_message(data):
    print('received message')
    print("[+] starting, time ",datetime.datetime.fromtimestamp(data["timestamp"]/1000))
    emit("progress" , {"data":"starting..."},json=True)
    if data["action"] == "start":
        main()
    elif data["action"] == "loop":
        loop_mode(data["reset_heat"],data["stream_cam"])
    elif data["action"] == "stop":
        global is_conntected
        is_conntected = False
@socketio.on('accuracy')
def handle_accuracy(data):
    global DIFFERENCE_RANGE
    DIFFERENCE_RANGE = int(data["accuracy"])

@socketio.on('divide_by')
def handle_divide_by(data):
    global RESIZER
    RESIZER = int(data["divide_by"])
    print(f"[+] Divide by {RESIZER}")

if __name__ == '__main__':
    socketio.run(app,port=8080,debug=True)
