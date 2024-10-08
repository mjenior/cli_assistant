
import re
import os
import requests
from openai import OpenAI
from datetime import datetime

from bin.lib import extDict

# Generate timestamp string
def gen_timestamp(time=True):
    date_time = str(datetime.now()).split()
    date = date_time[0].split('-'); time = date_time[1].split('.')[0]
    date = f"{int(date[1])}_{int(date[2])}_{int(date[0])}"; time = time.replace(':','')
    
    if time:
        return f"{date}.{time}"
    else:
        return date

    # Assemble query
def assemble_query(vars):
    query = [{"role": "user", "content": vars['prompt']}, {"role": "system", "content": vars['role']}]
    if len(vars['reflection']) > 0: query.append({"role": "assistant", "content": vars['reflection']})

    return query


def submit_query(vars):
    
    client = OpenAI()
    if vars['label'] != "artist":
        response = client.chat.completions.create(model=vars['model'], messages=vars['query'])
        message = response.choices[0].message.content
        if vars['verbose']: print(f"Response:\n{message}")
        if vars['code']:
            scripts = pull_code(message)
            if len(scripts) > 0:
                    print('\nCode identified and saved separately:')
                    for x in scripts:
                        print(f"\t{x}")
    else:
        response = client.images.generate(model=vars['model'], prompt=vars['prompt'], n=1, 
                                        size=vars['size'], quality=vars['quality'])
        message = response.data[0].revised_prompt
        if vars['verbose']: print(f"Revise prompt:\n{message}")
        image_data = requests.get(response.data[0].url)
        image_file = f"{vars['model'].replace('-','')}.{vars['timestamp']}.image.png"
        print('\nGenerated image saved to:', image_file)
        with open(image_file,'wb') as outFile: outFile.write(image_data.content)

    outFile = f"{vars['label']}.{vars['model'].replace('-','')}.{vars['timestamp']}.response.txt"
    print(f'\nCurrent response text saved to:\n\t{outFile}\n')
    with open(outFile, "w") as outFile: outFile.write(message)


def script_name(text):

    func = text.split()[1].split('(')[0].lower()
    func = re.sub('[^0-9a-zA-Z]+', '_', func)

    if func in ['','main','function']:
        return 'script'
    else:
        return func


# Find code snippets in responses and save to separate scripts with appropriate file extensions
def pull_code(response, extensions=extDict):
    os.makedirs('code', exist_ok=True)

    code_found = False; code = ''; count = 0; outFiles = []
    lines = response.split('\n')
    for line in lines:
        if len(line.strip()) == 0:
            continue

        if line.startswith('```') and code_found == False:
            code_found = True; count += 1; code = ''; funcNames = []
            lang = line.replace('```','').lower().split()[0]
            try:
                ext = extensions[lang]
            except KeyError:
                ext = lang

        elif line.startswith('```') and code_found == True:
            name_ext = max(funcNames, key=len)
            codeFile = f"code/{name_ext}.{count}{ext}"
            code_found = False
            outFiles.append(codeFile)
            if codeFile.startswith('_'): codeFile = codeFile.lstrip('_')
            if len(code.split('\n')) > 2:
                with open(codeFile, "w") as outFile:
                    outFile.write(code)
        
        elif code_found == True:
            code += f"{line}\n"
            if "def " in line:
                funcNames.append(script_name(line))

    return outFiles


