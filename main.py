import os
import ast
from utils import clean_dir
from constants import DEFAULT_DIR, DEFAULT_MODEL, DEFAULT_MAX_TOKENS
import time


@stub.function(
    image=openai_image,
    secret=modal.Secret.from_dotenv(),
    retries=modal.Retries(
        max_retries=3,
        backoff_coefficient=2.0,
        initial_delay=1.0,
    ),
    # concurrency_limit=5,
    # timeout=120,
)
def generate_response(system_prompt, user_prompt, *args):
    import openai
    import tiktoken

    def reportTokens(prompt):
        encoding = tiktoken.encoding_for_model(openai_model)
        print("\033[37m" + str(len(encoding.encode(prompt))) + " tokens\033[0m" + " in prompt: " + "\033[92m" + prompt[:50] + "\033[0m")

    openai.api_key = os.environ["OPENAI_API_KEY"]

    messages = []
    messages.append({"role": "system", "content": system_prompt})
    reportTokens(system_prompt)
    messages.append({"role": "user", "content": user_prompt})
    reportTokens(user_prompt)
    role = "assistant"
    for value in args:
        messages.append({"role": role, "content": value})
        reportTokens(value)
        role = "user" if role == "assistant" else "assistant"

    params = {
        "model": openai_model,
        "messages": messages,
        "max_tokens": openai_model_max_tokens,
        "temperature": 0,
    }

    response = openai.ChatCompletion.create(**params)
    time.sleep(5)  # Add a delay of 1 second between API calls
    reply = response.choices[0]["message"]["content"]
    return reply


@stub.function()
def generate_file(filename, model=DEFAULT_MODEL, filepaths_string=None, shared_dependencies=None, prompt=None):
    # call openai api with this prompt
    filecode = generate_response.call(model, 
        f"""You are an AI developer who is trying to write a program that will generate code for the user based on their intent.
        
    the app is: {prompt}

    the files we have decided to generate are: {filepaths_string}

    the shared dependencies (like filenames and variable names) we have decided on are: {shared_dependencies}
    
    only write valid code for the given filepath and file type, and return only the code.
    do not add any other explanation, only return valid code for that file type.
    """,
        f"""
    We have broken up the program into per-file generation. 
    Now your job is to generate only the code for the file {filename}. 
    Make sure to have consistent filenames if you reference other files we are also generating.
    
    Remember that you must obey 3 things: 
       - you are generating code for the file {filename}
       - do not stray from the names of the files and the shared dependencies we have decided on
       - MOST IMPORTANT OF ALL - the purpose of our app is {prompt} - every line of code you generate must be valid code. Do not include code fences in your response, for example
    
    Bad response:
    ```javascript 
    console.log("hello world")
    ```
    
    Good response:
    console.log("hello world")
    
    Begin generating the code now.

    """,
    )

    return filename, filecode


@stub.local_entrypoint()
def main(prompt, directory=DEFAULT_DIR, model=DEFAULT_MODEL, file=None):
    # read file from prompt if it ends in a .md filetype
    if prompt.endswith(".md"):
        with open(prompt, "r") as promptfile:
            prompt = promptfile.read()

    print("hi its me, 🐣the smol developer🐣! you said you wanted:")
    # print the prompt in green color
    print("\033[92m" + prompt + "\033[0m")

    # call openai api with this prompt
    filepaths_string = generate_response.call(model, 
        """You are an AI developer who is trying to write a program that will generate code for the user based on their intent.
        
    When given their intent, create a complete, exhaustive list of filepaths that the user would write to make the program.
    
    only list the filepaths you would write, and return them as a python list of strings. 
    do not add any other explanation, only return a python list of strings.

    Example output:
    ["index.html", "style.css", "script.js"]
    """,
        prompt,
    )
    print(filepaths_string)
    # parse the result into a python list
    list_actual = []
    try:
        list_actual = ast.literal_eval(filepaths_string)

        # if shared_dependencies.md is there, read it in, else set it to None
        shared_dependencies = None
        if os.path.exists("shared_dependencies.md"):
            with open("shared_dependencies.md", "r") as shared_dependencies_file:
                shared_dependencies = shared_dependencies_file.read()

        if file is not None:
            # check file
            print("file", file)
            filename, filecode = generate_file(file, model=model, filepaths_string=filepaths_string, shared_dependencies=shared_dependencies, prompt=prompt)
            write_file(filename, filecode, directory)
        else:
            clean_dir(directory)

            # understand shared dependencies
            shared_dependencies = generate_response.call(model, 
                """You are an AI developer who is trying to write a program that will generate code for the user based on their intent.
                
            In response to the user's prompt:

            ---
            the app is: {prompt}
            ---
            
            the files we have decided to generate are: {filepaths_string}

            Now that we have a list of files, we need to understand what dependencies they share.
            Please name and briefly describe what is shared between the files we are generating, including exported variables, data schemas, id names of every DOM elements that javascript functions will use, message names, and function names.
            Exclusively focus on the names of the shared dependencies, and do not add any other explanation.
            """,
                prompt,
            )
            print(shared_dependencies)
            # write shared dependencies as a md file inside the generated directory
            write_file("shared_dependencies.md", shared_dependencies, directory)
            
            # Iterate over generated files and write them to the specified directory
            for filename, filecode in generate_file.map(
                list_actual, order_outputs=False, kwargs=dict(model=model, filepaths_string=filepaths_string, shared_dependencies=shared_dependencies, prompt=prompt)
            ):
                write_file(filename, filecode, directory)


    except ValueError:
        print("Failed to parse result")


def write_file(filename, filecode, directory):
    # Output the filename in blue color
    print("\033[94m" + filename + "\033[0m")
    print(filecode)
    
    file_path = os.path.join(directory, filename)
    dir = os.path.dirname(file_path)

    # Check if the filename is actually a directory
    if os.path.isdir(file_path):
        print(f"Error: {filename} is a directory, not a file.")
        return

    os.makedirs(dir, exist_ok=True)

    # Open the file in write mode
    with open(file_path, "w") as file:
        # Write content to the file
        file.write(filecode)

