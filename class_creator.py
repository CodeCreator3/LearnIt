import ollama
import json
import random
import re

def create_class(class_name: str):
    units = message_to_json(ask_question(input="Please create a json file with an array containing the unit names for a college class called " + class_name + ". The format for the name of each unit should be \"Unit X: [Unit Name]\". The json file should be in the format {\"units\": [array of unit names]}. Please respond with only the json file and nothing else."))

    output_class = full_class(class_name)

    for unit_name in units["units"]:
        new_unit = unit(unit_name)
        lessons = message_to_json(ask_question(input="Please create a json file with an array containing the lesson names for a college class unit called " + unit_name + ". The format for the name of each lesson should be Lesson X: [Lesson Name]. The json file should be in the format {\"lessons\": [array of lesson names]}. Please respond with only the json file and nothing else."))
        print(unit_name)
        for lesson_name in lessons["lessons"]:
            print("  " + lesson_name)
            content = ask_question(input="Please create the content for a college class lesson called " + lesson_name + ". The content should be in markdown format and should include headings, subheadings, bullet points, and code snippets where appropriate. Please respond with only the markdown content and nothing else. Do not provide example or filler content. You are speaking directly to a student.")
            print("    Content: " + content)
            new_lesson = lesson(lesson_name, content)
            practice_problems_response = ask_question(input="Please practice problems and their solutions for a college class lesson called " + lesson_name + " in a unit called " + unit_name + ". Start each question with Q: and each answer with A: ")
            practice_problems = parse_qa(practice_problems_response)
            for problem in practice_problems:
                print("    Problem: "  + problem[0])
                print("    Solution: "  + problem[1])
                new_problem = practice_problem(problem[0], problem[1])
                new_lesson.practiceProblems.append(new_problem)
            new_unit.lessons.append(new_lesson)
        output_class.units.append(new_unit)

    return output_class

def ask_question(input: str) -> str:

    response = ollama.chat(
        model="llama3",
        messages=[
            {"role": "system", "content": input + " /n Please answer in markdown format."}
        ],
        options={
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 50,
            "seed": random.randint(1, 1_000_000)  # Random seed each run
        }
    )

    return response["message"]["content"]


def _revise_json_str(json_str: str, error: str) -> str:
    revised = ask_question(input="You are a professional in JSON format. The following json file has an error: " + error + ". Please revise the json file to fix the error. The json file is: " + json_str + ". Your output json must be different than the last json file I provided you. If you are unsure how to fix the error, you may delete that element of the json. Before you output the json include the reasoning for your change after the marker \"-r\", this must be BEFORE the JSON file in your message. Here's a paragraph summarizing the rules of JSON: JSON (JavaScript Object Notation) represents data using objects and arrays. An object is a collection of key-value pairs enclosed in curly braces `{}`, where keys must be strings in double quotes and values can be a string, number, boolean, null, object, or array. Each key-value pair is separated by a comma. An array is an ordered list of values enclosed in square brackets `[]`, with elements separated by commas and values allowed to be any valid JSON type. Strings must use double quotes and can include escaped characters like `\"`, `\\`, `\n`, or `\t`. Numbers can be integers or decimals, may be negative, cannot have leading zeros (except zero itself), and can use scientific notation. Boolean values are `true` or `false`, and `null` represents the absence of a value. Whitespace outside strings is ignored, trailing commas are not allowed, and keys within an object must be unique.")
    # Extract JSON from response
    print("Revised JSON full output: \n", revised + "\n")
    reasoningstart = revised.find("-r")
    start = revised.find("{")
    end = revised.rfind("}")
    reasoning = revised[reasoningstart+2:start].strip() if reasoningstart != -1 and start != -1 and reasoningstart < start else ""
    print ("Revision reasoning: ", reasoning)
    if start != -1 and end != -1 and end > start:
        revised_json = revised[start:end+1]
    else:
        revised_json = revised
    return revised_json

def message_to_json(message: str) -> dict:
    # Find the first "{"
    start = message.find("{")
    end = message.rfind("}")

    json_found = start != -1 and end != -1 and end > start

    if(not json_found):
        print("ERROR: No JSON found in the message: ")
        print(message)
        return {}

    # Slice from there to the end
    result = message[start:end + 1] if json_found else message

    max_attempts = 3
    attempt = 0
    last_result = result
    while attempt < max_attempts:
        try:
            output = json.loads(last_result)
            return output
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error (attempt {attempt+1}): ", e)
            print("Offending json: \n", last_result)
            revised = _revise_json_str(last_result, str(e))
            # If revision didn't change anything, break
            if revised.strip() == last_result.strip():
                print("Revision did not change output. Stopping attempts.")
                break
            last_result = revised
            attempt += 1
    print("Failed to parse JSON after max attempts.")
    return {}

def parse_qa(text):
    # This regex matches Q: ... A: ... pairs, even across multiple lines
    pattern = r"Q:\s*(.*?)\s*A:\s*(.*?)(?=Q:|$)"
    matches = re.findall(pattern, text, re.DOTALL)
    # Returns a list of (question, answer) tuples
    return [(q.strip(), a.strip()) for q, a in matches]

class full_class:
    def __init__(self, class_name: str):
        self.class_name = class_name
        self.units = []

class unit:
    def __init__(self, unit_name: str):
        self.unit_name = unit_name
        self.lessons = []

class lesson:
    def __init__(self, lesson_name: str, content: str = ""):
        self.lesson_name = lesson_name
        self.practiceProblems = []
        self.content = content

class practice_problem:
    def __init__(self, problem: str, solution: str):
        self.problem = problem
        self.solution = solution