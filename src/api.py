import re
import os
import requests
from collections import defaultdict

from openai import OpenAI

from src.lib import extDict, rewrite_options, refine_message

class OpenAIInterface():
    """
    Handles OpenAI API interactions including assembling, submitting, and processing queries.
    """

    def __init__(self, manager):
        """
        Initializes the query handler with the provided variables.
        """
        # Inherit core properties
        self.prompt = manager.prompt
        self.role = manager.role
        self.label = manager.label
        self.reflection = manager.reflection
        self.silent = manager.silent
        self.timestamp = manager.timestamp
        self.model = manager.model
        self.code = manager.code
        self.log = manager.log
        self.log_text = manager.log_text
        self.transcript_file = manager.transcript_file
        self.size = manager.size
        self.quality = manager.quality
        self.iterations = manager.iterations
        self.prefix = manager.prefix 
        self.print_response = True

        # Initialize client
        self.client = OpenAI()

        # Finalize query
        if manager.refine:
            self.prompt = self.refine_prompt()
        self.query = self._assemble_query()
        
    def _assemble_query(self):
        """
        Assembles the query dictionary for the API request.
        """
        query = [
            {"role": "user", "content": self.prompt},
            {"role": "system", "content": self.role}
        ]
        if self.reflection:
            query.append({"role": "assistant", "content": self.reflection})
        
        return query

    def submit_query(self):
        """
        Submits the query to OpenAI's API and processes the response.
        """
        if not self.silent:
            print("\nSubmitting User query...\n")
        if self.log:
            self.log_text.append("\nSubmitting User query...\n")

        if self.label not in ["artist", "photo"]:
            return self._process_text_response()
        else:
            return self._process_image_response()

    def _process_text_response(self):
        """
        Processes text-based responses from OpenAI's chat models.
        """
        self.reponse_type = "reponse"
        response = self.client.chat.completions.create(
            model=self.model, messages=self.query, n=self.iterations,
        )
        message = self.condense_iterations(response)

        if self.print_response:
            print(f"\nResponse:\n{message}\n")

        if self.code:
            os.makedirs('code', exist_ok=True)
            scripts = self._extract_code_from_reponse(message, self.timestamp)
            if scripts:
                if not self.silent:
                    print(f"\nCode extracted from reponse text and saved to:\n\t{'\n\t'.join(scripts)}\n")
                if self.log:
                    self.log_text.append(f"\nCode extracted from reponse text and saved to:\n\t{'\n\t'.join(scripts)}\n")

    def _process_image_response(self):
        """
        Processes image generation requests using OpenAI's image models.
        """
        self.reponse_type = "revised_prompt"
        os.makedirs('images', exist_ok=True)
        response = self.client.images.generate(
            model=self.model, prompt=self.prompt,
            n=1, size=self.size, quality=self.quality)
        revised_prompt = response.data[0].revised_prompt
        if not self.silent:
            print(f"Revised prompt:\n{revised_prompt}")
        if self.log:
            self.log_text.append(f"Revised prompt:\n{revised_prompt}")

        image_data = requests.get(response.data[0].url).content
        image_file = f"images/{self.prefix}.image.png"
        with open(image_file, 'wb') as outFile:
            outFile.write(image_data)
        if not self.silent:
            print(f"\nGenerated image saved to: {image_file}")
        if self.log:
            self.log_text.append(f"\nGenerated image saved to: {image_file}")

    def save_chat_transcript(self):
        """
        Saves the current response text to a file if specified.
        """
        outFile = f"transcripts/{self.prefix}.transcript.log"
        os.makedirs('transcripts', exist_ok=True)
        with open(self.transcript_file, "a", encoding="utf-8") as file:
            file.write("\n".join(self.log_text))

        if not self.silent:
            print(f"\nResponse transcript text saved to: {outFile}")

    def _extract_code_from_reponse(self, response, timestamp):
        """
        Extracts and saves code snippets from the response into separate files.
        """
        # Initialize variables
        pyObjects = defaultdict(list)
        pyObjects["current_code"] = ["# Code generated by ChatGPT\n"]

        # Split response into lines and process
        for line in response.splitlines():
            line = line.strip()

            # Start or end of a code block
            counter = 0
            if line.startswith("```"):
                if len(pyObjects["current_code"]) > 2:  # End of a code block
                    pyObjects["code"] = "\n".join(pyObjects["current_code"])

                    # Determine output filename
                    counter += 1
                    name = self._select_outfile_ext(pyObjects['classes'], pyObjects['functions'], lang)
                    file_name = f"code/{name}.{timestamp}.{counter}{extDict.get(lang, f".{lang}")}".lstrip('_')
                    pyObjects['files'].append(file_name)

                    # Save code snippet to file
                    os.makedirs("code", exist_ok=True)
                    with open(file_name, "w", encoding="utf-8") as file:
                        file.write(pyObjects["code"])

                    # Reset code accumulator
                    pyObjects["current_code"] = ["# Code generated by ChatGPT\n"]

                else:  # Start of a new code block
                    lang = line.replace("```", "").lower()
                    pyObjects["current_code"].append(lang.capitalize())

            # Process lines within a code block
            elif len(pyObjects["current_code"]) > 1:
                pyObjects["current_code"].append(line)
                if len(line.strip()) > 0 and line.split()[0] in ['def', 'class']:
                    f, c = self._scrape_object_name(line)
                    pyObjects['functions'].append(f)
                    pyObjects['classes'].append(c)

        return pyObjects["files"]

    @staticmethod
    def _select_outfile_ext(classes, funcs, lng):
        """
        Select name for code files based on generated functions and classes
        """
        classes = [x for x in classes if len(x.strip()) >= 1]
        funcs = [x for x in funcs if len(x.strip()) >= 1]
        if len(classes) != 0:
            name = max(classes, key=len, default=lng)
        else:
            name = max(funcs, key=len, default=lng)

        return max([name, 'code'], key=len)

    @staticmethod
    def _scrape_object_name(line):
        """
        Extracts a meaningful name for a script or class from the provided line of text.
        """
        name = line.split()[1].split('(')[0].lower()
        name = re.sub(r'[^0-9a-zA-Z]+', '_', name)
    
        func, clss = '', ''
        if line.startswith("def ") and " main(" not in line:
            func = name
        elif line.startswith("class "):
            clss = name

        return func, clss

    def condense_iterations(self, api_response, sys_text=refine_message):
    
        api_responses = [r.message.content.strip() for r in api_response.choices]
        if len(api_responses) > 1:
            condensed = self.client.chat.completions.create(
                model=self.model,
                messages = [
                    {"role": "system", "content": sys_text},
                    {"role": "user", "content": "\n\n".join(api_responses)}])
            

            return condensed.choices[0].message.content.strip()
        else:
            return api_responses[0]

    def refine_prompt(self, actions=['expand','amplify'], temp=0.7):
        """
        Refines an LLM prompt using specified rewrite actions.
        
        Parameters:
            prompt (str): The original prompt to be refined.
            actions (list of str): A list of rewrite actions (keys from the rewrite_options dictionary).
            api_key (str): Your OpenAI API key.
            model (str): The OpenAI model to use for refining the prompt (default is "gpt-4").
        
        Returns:
            dict: A string containing the refined prompt
        """
        if not self.silent:
            print("\nRefining initial prompt...")
        
        # Check prompt for additional action keywords
        actions = set(actions)
        words = set([re.sub(r'[^\w\s]','', word).lower() for word in self.prompt.split() if len(word) >= 1])
        actions |= set(rewrite_options.keys()).intersection(words)
        action_str = ""
        for a in actions:
            action_str += f"{a}; {rewrite_options[a]}\n"

        # Generate the system message for the action
        updated_message = refine_message + f"Rewrite the input prompt based on the instruction: {action_str}"
        if self.role: # Add specific expertise if provided
            updated_message += self.role
        
        # Make an API call to refine the prompt over X iterations:
        refined = self.client.chat.completions.create(
            model=self.model, temperature=temp, n=self.iterations,
            messages=[
                {"role": "system", "content": updated_message},
                {"role": "user", "content": self.prompt}])

        # Parse iterations and synthesize for more optimal response
        final = self.condense_iterations(refined)

        if self.print_response:
            print(f'\nRefined prompt:\n{final}')
        
        # Update the refined prompt with the response
        return final
