import base64
from io import BytesIO
import os
import re
import modules.scripts as scripts
import modules.scripts_postprocessing as scripts_postprocessing
import modules.shared as shared
from modules.shared import opts
from modules import script_callbacks
from modules.ui_components import ToolButton
import gradio as gr
import requests
import time
import configparser
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)
is_debug = False

def dprint(s):
    logger.info(s)
    

class GrowingList(list):
    def __setitem__(self, index, value):
        if index >= len(self):
            self.extend([""]*(index + 50 - len(self)))
        list.__setitem__(self, index, value)

# when using dynamic prompts we have to save the actual prompt used for image n
upload_prompts =  GrowingList()
global_for_manual_upload = {}
global_for_download_parameters = {}
global_ui = {}
global_extra_image = None
loaded_count = 0
last_prompt = ""
last_seed = 0
last_batch = 0
last_model = ""
the_set_timestamp = ""
the_re_extra_net = re.compile(r"<(\w+):([^>]+)>")    # copied from rxtra_networks.py
type_of_gr_update = type(gr.update())
xthe_rest_url ="https://kcd4tcn593.execute-api.us-east-1.amazonaws.com/ProdV1/"
the_rest_url = "https://e6h2r5adh8.execute-api.us-east-1.amazonaws.com/prod/"

def on_ui_settings1():
    dprint("on_ui_settings1")
    section = "gadzoinks", "Gadzoinks"
    shared.opts.add_option(
        key="gz_handle",
        info=shared.OptionInfo(
            "",
            label="Enter your handle (you can find this in the app settings->account)",
            section=section,
        ),
    )

    shared.opts.add_option(
        key="gz_authkey",
        info=shared.OptionInfo(
            "",
            label="Enter your Authkey (you can find this in the app settings->account)",
            section=section,
        ),
    )
    shared.opts.add_option(
        key="gz_private",
        info=shared.OptionInfo(
            False,
            label="Enable for private upload. You must have enabled this feature in the app",
            section=section,
        ),
    )
    shared.opts.add_option(
        key="gz_uploadimages",
        info=shared.OptionInfo(
            True,
            label="Upload new images. turn this off to disable cloud storage",
            section=section,
        ),
    )
    shared.opts.add_option(
    key="gz_age",
    info=shared.OptionInfo(
        "4+",
        "Age rating for uploaded images",
        gr.Radio,
        {"choices": ["4+", "12+", "17+"]},
        section=section
    ),
)
    
def printStruct(struc, indent=0):
   if isinstance(struc, dict):
     print ('  '*indent+'{')
     for key,val in struc.items():
       if isinstance(val, (dict, list, tuple)):
         print ('  '*(indent+1) + str(key) + '=> ')
         printStruct(val, indent+2)
       else:
         print ('  '*(indent+1) + str(key) + '=> ' + str(val))
     print ('  '*indent+'}')
   elif isinstance(struc, list):
     print ('  '*indent + '[')
     for item in struc:
       printStruct(item, indent+1)
     print ('  '*indent + ']')
   elif isinstance(struc, tuple):
     print ('  '*indent + '(')
     for item in struc:
       printStruct(item, indent+1)
     print ('  '*indent + ')')
   else: print ('  '*indent + str(struc))

# image is BytesIO
def uploadDesc(image_bytes, desc,acount_handle,auth_key):
    global last_batch
    try:
        dprint(f"uploadDesc() desc:{desc}")
        for key, value in desc.items():
            if callable(value):
                dprint(f"{key} is a function named {value.__name__}")
            else:
                dprint(f"{key} == {value}")
        
        headers = {'Accept': 'application/json', 'content-type':'application/json',
                   'X-Gadzoink-handle':acount_handle,  'X-Gadzoink-auth':auth_key}

        dprint(f"uploadDesc last_batch {last_batch}")

        if last_batch == 0:
            dprint("YES last_batch == 0:")
            desc["start_of_set"] = 1     # first image in this batch/set, so let backend know 
        dprint(f"upDesc {desc}")
        resp = requests.post(the_rest_url +'uploadimage',json=desc, headers=headers)
        j = resp.json()
        dprint(resp.status_code)
        dprint(f"resp.json:{j}")
        status = j.get("status",500)
        if status == 200:
            url = j["url"]
            dprint(f"url {url}")
            fields = j["fields"]
            dprint( f"fields {fields}" )
            files = {'file': image_bytes }
            http_response = requests.post(url, data=fields , files=files )
        elif status == 403:
            msg = j.get("message","unknown error uploading file")
            gr.Warning(f"Gadzoinks Extension upload failed.  {msg}")
    except Exception as e:
        gr.Warning(f"Gadzoinks Extension upload failed. exception {e}")
        print(f"Gadzoinks Extension upload failed. exception {e}\n ")

def Zupload(image_bytes,name,handle,auth_key,app,extra_generation_params,model,prompt,negative_prompt ,seed ,steps , sampler, cfg_scale , denoising_strength, size, imgType,set_name,maturity_rating, private_upload_state):
    if denoising_strength is None:
        denoising_strength = 0.0
    desc = { "filename" : name, "handle" : handle , "app" : app , "model" : model ,
            "prompt" : prompt, "negative_prompt" :negative_prompt , "seed" : seed ,
            "steps" : steps , "sampler" : sampler, "cfg_scale" : cfg_scale , "denoising_strength":denoising_strength,
            "width" :size[0] , "height" : size[1], "maturity_rating" : maturity_rating ,
            "set_name" : set_name, "set_timestring" : the_set_timestamp,
           "imageType" : imgType , "visibility" : int(private_upload_state) }
    desc["model"] = extra_generation_params.pop("gadzoinks_primary_model","NoModel")
    for k,v in extra_generation_params.items():
        dprint( f"upload()  extra_generation_params {k}={v}")
        desc[k] = v
    dprint( f"upload() desc:{desc}")
    uploadDesc(image_bytes,desc,handle,auth_key)

'''
use imageBytes it might not be same as kwargs['image_bytes']
'''
def upload(imageBytes, **kwargs):
    auth_key =  kwargs.get("auth_key")
    handle =  kwargs.get("handle", kwargs.get("acount_handle"))
    desc = {
        "filename": kwargs.get("name"),
        "handle": handle,
        "app": kwargs.get("app"),
        "model": kwargs.get("model"),
        "prompt": kwargs.get("prompt"),
        "negative_prompt": kwargs.get("negative_prompt"),
        "seed": kwargs.get("seed"),
        "steps": kwargs.get("steps",20),
        "sampler": kwargs.get("sampler"),
        "cfg_scale": kwargs.get("cfg_scale",7.0),
        "denoising_strength": kwargs.get("denoising_strength", 0.0),
        "width": kwargs.get("size", [None, None])[0],
        "height": kwargs.get("size", [None, None])[1],
        "maturity_rating": kwargs.get("maturity_rating"),
        "set_name": kwargs.get("set_name"),
        "set_timestring": kwargs.get("the_set_timestamp"),
        "imageType": kwargs.get("imgType"),
        "visibility": int(kwargs.get("private_upload_state", 0)),
    }

    extra_generation_params = kwargs.get("extra_generation_params", {})
    desc["model"] = extra_generation_params.pop("gadzoinks_primary_model", "NoModel")
    #TODO I cannot get extra_generation_params["Hires prompt"]
    # to work, so I am just skipping it
    for k, v in extra_generation_params.items():
        if callable(v):
            dprint(f"upload() {k} is a function named {v.__name__}  SKIPPING")
        else:
            desc[k] = v
            dprint(f"upload() extra_generation_params {k}={desc[k]}")
    dprint(f"upload() desc: {desc}")
    uploadDesc(imageBytes,desc,handle,auth_key)
    
def tpl_upload_button_click():
    #print(f"tpl_upload_button_click()")
    doUpload()

def buttonGetParamsClick():
    dprint(f"buttonGetParamsClick")
    pass

def upload_button_click(acount_handle,auth_key,set_name,maturity_rating):
    global global_for_manual_upload,global_extra_image
    dprint(f"toolbar upload_button_click {acount_handle} {auth_key} {set_name}, {maturity_rating}")
    image_bytes = None
    if  global_extra_image:
        dprint("have global_extra_image")
        buffer = BytesIO()
        global_extra_image.save(buffer, "png")
        image_bytes = buffer.getvalue()
    else:
        image_bytes = global_for_manual_upload.get('image_bytes')
        dprint("trying  global_for_manual_upload.get('image_bytes')")
    dprint(f"image_bytes type {type(image_bytes)}")
    dprint(f"image_bytes {len(image_bytes)}")
    if not image_bytes:
        dprint(f"upload_button_click NO IMAGE")
        return
    upload(image_bytes, **global_for_manual_upload)
    
def Zupload_button_click(acount_handle,auth_key,set_name,maturity_rating):
    global global_for_manual_upload,global_extra_image
    print(f"toolbar upload_button_click {acount_handle} {auth_key} {set_name}, {maturity_rating}")
    image_bytes = None
    if  global_extra_image:
        dprint("have global_extra_image")
        buffer = BytesIO()
        global_extra_image.save(buffer, "png")
        image_bytes = buffer.getvalue()
    else:
        image_bytes = global_for_manual_upload.get('image_bytes')
    if not image_bytes:
        print(f"upload_button_click NO IMAGE")
        return
    upload(image_bytes,
           global_for_manual_upload['name'],
           global_for_manual_upload['acount_handle'],
           global_for_manual_upload['auth_key'] ,
           global_for_manual_upload['app'],
           global_for_manual_upload['extra_generation_params'],
           global_for_manual_upload['model'] ,
           global_for_manual_upload['prompt'] ,
           global_for_manual_upload['neg_prompt']  ,
           global_for_manual_upload['seed'] ,
           global_for_manual_upload['steps'] ,
           global_for_manual_upload['sampler'], 
           global_for_manual_upload['cfg_scale']  , 
           global_for_manual_upload['denoising_strength']  , 
           global_for_manual_upload['size'],
           global_for_manual_upload['imgType'] ,
           global_for_manual_upload.get("set_name" ,""),
           global_for_manual_upload['maturity_rating'] ,
           global_for_manual_upload['private_upload'] )

def buildDownloadButton(download_button):
    global global_for_manual_upload
    dprint("buildDownloadButton")
    paste_fields = [
        (global_for_download_parameters["txt2img_prompt"], "prompt"),
         (global_for_download_parameters["txt2img_neg_prompt"], "negative_prompt"),
         (global_for_download_parameters["txt2img_sampling"], "sampler"),
         (global_for_download_parameters["txt2img_cfg_scale"], "cfg_scale"),
         (global_for_download_parameters["txt2img_denoising_strength"], "denoising_strength"),
         (global_for_download_parameters["txt2img_width"], "width"),
         (global_for_download_parameters["txt2img_height"], "height"),
         (global_for_download_parameters["txt2img_seed"], "seed"),
         (global_for_download_parameters["txt2img_steps"], "steps"),
         (global_for_download_parameters["txt2img_hr_upscaler"],"hires_upscaler"),
         (global_for_download_parameters["txt2img_hires_steps"],"hires_steps"),
         (global_for_download_parameters["txt2img_hr_scale"],"hires_upscale"),
         (global_for_download_parameters["txt2img_checkpoint"],"refiner"),
         (global_for_download_parameters["txt2img_switch_at"],"refiner_switch_at"),

    ]
    def dnload_button_click(acount_handle,auth_key,set_name,maturity_rating):
        print(f"toolbar dnload_button_click {acount_handle} {auth_key} {set_name}, {maturity_rating}")
        # rest call
        headers = {'Accept': 'application/json', 'content-type':'application/json',
            'X-Gadzoink-handle':acount_handle,  'X-Gadzoink-auth':auth_key}
        resp = requests.post(the_rest_url + 'getparameters',json={}, headers=headers)
        j = resp.json()
        dprint(f" status:{resp.status_code} j:{j}")
        params = j["payload"] # { 'Prompt': 'wombat','Negative prompt': 'ugly' }
        res = []
        for output, key in paste_fields:
            if callable(key):
                v = key(params)
            else:
                v = params.get(key, None)
            print( f"dnload_button_click key:{key} v:{v}")
            if v is None:
                res.append(gr.update())
            elif isinstance(v, type_of_gr_update):
                res.append(v)
            else:
                try:
                    valtype = type(output.value)

                    if valtype == bool and v == "False":
                        val = False
                    else:
                        val = valtype(v)
                    #res.append(v)
                    res.append(gr.update(value=val))
                except Exception:
                    res.append(gr.update())
        print(f"dnload_button_click  res:{res}")
        return res

    download_button.click(fn=dnload_button_click,
        inputs=[ global_ui['acount_handle'],global_ui['auth_key'],
        global_ui['set_name'],global_ui['maturity_rating']],
        outputs=[x[0] for x in paste_fields],
        show_progress=False )

#[global_for_download_parameters["txt2img_prompt" ]] )



'''
Callbacks
'''

'''
def register_pnginfo_saver(pnginfo_saver: PngInfoSaver) -> None:
    def on_save(image_save_params: ImageSaveParams) -> None:
        dprint("register_pnginfo_saver on_save")
    script_callbacks.on_before_image_saved(on_save)


def register_prompt_writer(prompt_writer: PromptWriter) -> None:
    def on_save(image_save_params: ImageSaveParams) -> None:
         dprint("register_prompt_writer on_save")
    script_callbacks.on_before_image_saved(on_save)
'''

def callback1(component):
    dprint(f"callback1 component:{component}")


class ScriptPostprocessing(scripts_postprocessing.ScriptPostprocessing):
    image = None
    def __init__(self):
        dprint("ScriptPostprocessing init")
        self.name = "gadzoinks"
        self.order = 2000


    def name(self):
        dprint("ScriptPostprocessing name")
        return "Gadzoinks"

    def ui(self):
        global global_ui
        dprint(f"gz_handle:{opts.gz_handle}")
        dprint(f"ScriptPostprocessing ui  global_ui:{global_ui}")
        tabname="extras"
        upload_button = ToolButton('👺', elem_id=f'{tabname}_gadzoinks_button3', tooltip="upload image to Gadzoinks.")
        upload_button.click(fn=upload_button_click,
            inputs=[ global_ui['acount_handle'],global_ui['auth_key'],
            global_ui['set_name'],global_ui['maturity_rating']], outputs=None)
        return {}

    def image_changed(a):
        dprint("ScriptPostprocessing image_changed")

# ScriptPostprocessing , PostprocessedImage
    def process(scriptPostprocessing , postprocessedImage):
        dprint("def process(scriptPostprocessing , postprocessedImage):")
        global global_extra_image
        if postprocessedImage.image:
            dprint(" have postprocessedImage.image " )
            global_extra_image = postprocessedImage.image
        image = postprocessedImage.image
        dprint(f"ScriptPostprocessing process scriptPostprocessing:{scriptPostprocessing} postprocessedImage:{postprocessedImage}")
        dprint(f"args_from:{scriptPostprocessing.args_from}")
        dprint(f"args_to:{scriptPostprocessing.args_to}")

'''
Class
'''
class Scripts(scripts.Script):
    def __init__(self):
        dprint("Scripts __init__")
        global loaded_count
        self.on_after_component_elem_id = [( "extras_send_to_img2img",callback1  )]  #add( {"extras_send_to_img2img",callback } )
        loaded_count += 1
        if loaded_count % 2 == 0:
            return
        dprint("Scripts __init__ 2")
        script_callbacks.on_ui_settings(on_ui_settings1)
    def title(self):
        return "Gadzoink Script"

    def setup(self, component, **kwargs):
        dprint(f"*** setup {kwargs}")
        on_ui_settings()
        
    def on_ui_tabs(self, component, **kwargs):
        dprint(f"*** on_ui_tabs {kwargs}")

    def on_app_started(self, component, **kwargs):
        dprint(f"*** on_app_started {kwargs}")

    def postprocess(self, p, processed, *args):
        dprint( f"postprocess")

    # p is StableDiffusionProcessingTxt2Img
    def after_extra_networks_activate(self, p, *args, **kwargs):
        dprint( f"after_extra_networks_activate")
        dprint( f"p:{p}" )
        dprint( f"p.sd_model_name:{p.sd_model_name}" )
        dprint( f"p.extra_generation_params:{p.extra_generation_params}" )
        p.extra_generation_params["gadzoinks_primary_model"] = p.sd_model_name
        global_for_manual_upload['extra_generation_params'] = p.extra_generation_params
    def setup(self, p, *args):
        dprint(f"setup")

    def callback(component):
        dprint(f"callback component:{component}")

    def after_component(self, component, **kwargs):
        global global_ui
        global global_for_download_parameters
        want = {"txt2img_prompt","txt2img_neg_prompt","txt2img_sampling", "txt2img_cfg_scale", "txt2img_denoising_strength", 
            "txt2img_width", "txt2img_height", "txt2img_seed", "txt2img_steps","txt2img_hr_upscaler","txt2img_hires_steps",
            "txt2img_hr_scale","txt2img_checkpoint","txt2img_switch_at"}
        #dprint(f"G1 after_component {component.elem_id}")
        
        if component.elem_id in want:
            global_for_download_parameters[component.elem_id] = component

        # Add button to both txt2img and img2img tabs
        if kwargs.get("elem_id") == "txt2img_send_to_extras" or kwargs.get("elem_id") == "img2img_send_to_extras":
            tabname = kwargs.get("elem_id").replace("_send_to_extras", "")
            dprint(f"after_component {tabname}")
            upload_button = ToolButton('👺', elem_id=f'{tabname}_gadzoinks_button', tooltip="upload image to Gadzoinks.")
            upload_button.click(fn=upload_button_click,
                inputs=[ global_ui['acount_handle'],global_ui['auth_key'],
                        global_ui['set_name'],global_ui['maturity_rating']], outputs=None)
            download_button = ToolButton('🔗' , elem_id=f'{tabname}_gadzoinks_dlbutton', tooltip="download parameters from  Gadzoinks.")
            buildDownloadButton(download_button)
        # add to Extras, make sure we only add once
        '''
        if kwargs.get("elem_id") == "txt2img_send_to_extras":
            tabname="extras"
            upload_button = ToolButton('👺', elem_id=f'{tabname}_gadzoinks_button2', tooltip="upload image to Gadzoinks.")
            upload_button.click(fn=upload_button_click,
                inputs=[ global_ui['acount_handle'],global_ui['auth_key'],
                        global_ui['set_name'],global_ui['maturity_rating']], outputs=None)
        '''
    def show(self, is_img2img):
        dprint("Scripts Show")
        return scripts.AlwaysVisible

    
    
    
    def ui(self, is_img2img):
        global global_ui
        dprint("Scripts UI")
        extra_generation_params = {}
        
        dprint(f"UI opts.gz_uploadimages: {opts.gz_uploadimages} opts.gz_handle:{opts.gz_handle} opts.gz_authkey{opts.gz_authkey}")
        with gr.Group():
            title="Gadzoinks"
            with gr.Accordion(title, open=False):
                with gr.Row():
                    is_auto_upload_enabled = gr.Checkbox(label="Auto Upload", value=getGZUploadimages)
                    is_private_upload_enabled = gr.Checkbox(label="Private Upload", value=getGZPrivate)
                    maturity_rating = gr.Radio(
                        choices=["4+", "12+", "17+"],
                        value=getGZAge,
                        label="Age Rating"
                    )
                acount_handle = gr.Textbox(label="Account Handle", value=getGZHandle,interactive=True)
                auth_key = gr.Textbox(label="Auth Key", value=getGZAuthkey)
                set_name = gr.Textbox(label="Set Name", value="")
        
        
        global_ui['acount_handle'] = acount_handle
        global_ui['auth_key'] = auth_key
        global_ui['set_name']= set_name
        global_ui['maturity_rating'] = maturity_rating
        return [is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating]

    
    
    def before_process_batch(self,p, is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating, **kwargs):
        dprint(f"before_process_batch  {p.prompt}")
        pass
    
    def process_batch(self,p, is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating, **kwargs):
        dprint("process_batch delegate")
        global the_set_timestamp
        global upload_prompts
        global last_prompt,last_seed,last_batch,last_model
        dprint(f"process_batch  {p.prompt}")
        for key, value in kwargs.items():
            try:
                if callable(value):
                    dprint(f"{key} is a function named {value.__name__}")
                else:
                    dprint("%s == %s" % (key, value))
            except Exception as e:
                dpring(f"Exception {e} with key:{key}")
        idx = kwargs['batch_number']
        if idx == 0:
            the_set_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        pr = kwargs["prompts"][0]
        #print(f" idx {idx} prompt {pr}")
        upload_prompts[kwargs['batch_number']] = kwargs["prompts"][0]
        dprint("D5")
        last_prompt = kwargs["prompts"][0]  # dynamic prompt set , lora stripped
        last_seed = kwargs["seeds"][0]
        last_batch =  kwargs["batch_number"]
        p.extra_generation_params["gadzoinks_maturity_rating"] = maturity_rating
        if set_name:
            p.extra_generation_params["gadzoinks_set_name"] = set_name
        dprint("D10")
        '''
        config_file = os.path.join(scripts.basedir(), "gadzoinks_config.json")
        try:
            with open(config_file, "w") as json_file:
                json.dump(p.extra_generation_params, json_file)
        except Exception as e:
            print( f"process_batch Exception {e}")
        '''
        
        
        
    def postprocess_batch(self,p,is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating, **kwargs):
        #print(f"postprocess_batch  {p.prompt}")
        #for key, value in kwargs.items():
        #    print("%s == %s" % (key, value))
        pass
        
    def postprocess_image(self,p,postprocessImageArgs,is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating):
        global global_for_manual_upload
        global last_prompt,last_seed,last_batch,last_model
        # p modules.processing.StableDiffusionProcessingTxt2Img(StableDiffusionProcessing)
        # pp PostprocessImageArgs
        dprint(f"postprocess_image  prompt: {p.prompt}")
        name =  f"{os.getpid()}{  int(time.time()*1000000) }"
        lorastr = ""
        def found(m):
            nonlocal lorastr
            lorastr =  f"{lorastr} <{m.group(1)}:{m.group(2)}> "
        rawprompt = p.prompt
        str = re.sub(the_re_extra_net, found, rawprompt)  # extra lora text
        dprint(f"postprocess_image: str={str} lorastr={lorastr}")
        prompt = last_prompt + " " + lorastr

        seed = last_seed
        neg_prompt = p.negative_prompt
        regex = r"Steps:.*$"
        steps = p.steps
        denoising_strength = p.denoising_strength
        sampler = p.sampler_name  #input_dict["Sampler"]
        cfg_scale = p.cfg_scale #float(input_dict["CFG scale"])
        size = tuple((p.width,p.height))
        model_hash = shared.sd_model.sd_model_hash #input_dict["Model hash"]
        model = shared.sd_model.sd_checkpoint_info.model_name
        dprint( f"p.extra_generation_params: {p.extra_generation_params}")
        # print( f"postprocess_image() model: {p.sd_model}")
        image = postprocessImageArgs.image
        buffer = BytesIO()
        image.save(buffer, "png")
        image_bytes = buffer.getvalue()
        dprint(f"image_bytes {len(image_bytes)}")
        global_for_manual_upload['image_bytes'] = image_bytes
        global_for_manual_upload['name'] = name
        global_for_manual_upload['acount_handle'] = acount_handle
        global_for_manual_upload['auth_key'] = auth_key
        global_for_manual_upload['private_upload'] = is_private_upload_enabled
        global_for_manual_upload['app'] = "automatic1111"
        global_for_manual_upload['model'] = model
        global_for_manual_upload['prompt'] = prompt
        global_for_manual_upload['neg_prompt'] = neg_prompt
        global_for_manual_upload['seed'] = seed
        global_for_manual_upload['steps'] = steps
        global_for_manual_upload['sampler'] = sampler
        global_for_manual_upload['cfg_scale'] = cfg_scale
        global_for_manual_upload['size'] = size
        global_for_manual_upload['imgType'] = "png"
        global_for_manual_upload['set_name'] = set_name if set_name is not None else ""
        global_for_manual_upload['maturity_rating'] = maturity_rating
        global_for_manual_upload['extra_generation_params'] = p.extra_generation_params
        global_for_manual_upload['denoising_strength'] = p.denoising_strength
        if not is_auto_upload_enabled:
            return
        '''
        upload(image_bytes,name,acount_handle,auth_key,'automatic1111', p.extra_generation_params, model,
            prompt ,neg_prompt ,seed ,steps , sampler, cfg_scale , denoising_strength 
            ,size,"png",set_name,maturity_rating, is_private_upload_enabled  )
        '''
        upload(image_bytes,
           name=name,
           handle=acount_handle,
           auth_key=auth_key,
           app='automatic1111',
           extra_generation_params=p.extra_generation_params,
           model=model,
           prompt=prompt,
           negative_prompt=neg_prompt,
           seed=seed,
           steps=steps,
           sampler=sampler,
           cfg_scale=cfg_scale,
           denoising_strength=denoising_strength,
           size=size,
           imgType="png",
           set_name=set_name,
           maturity_rating=maturity_rating,
           private_upload_state=is_private_upload_enabled,
           the_set_timestamp=the_set_timestamp)

    def postprocess(self, p, processed,is_auto_upload_enabled,is_private_upload_enabled,acount_handle,auth_key,set_name,maturity_rating):
        global upload_prompts
        generation_info_js = processed.js()
        dprint( f"processed.js: ")
        dprint(generation_info_js)
        return True
    
def getGZHandle():
    return opts.gz_handle
def getGZAuthkey():
    return opts.gz_authkey
def getGZUploadimages():
    return opts.gz_uploadimages
def getGZPrivate():
    return opts.gz_private
def getGZAge():
    return opts.gz_age


# main
script_callbacks.on_ui_settings(on_ui_settings1)
is_debug = getattr(opts, "is_debug", False)
is_debug=False
if is_debug:
    logger.setLevel(logging.DEBUG)   # not using logger yet
    
