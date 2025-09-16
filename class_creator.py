import ollama
import json
import random
import re
import threading
import time
import os

def create_class(class_name: str, progress_callback=None):
    """Generate a class. If progress_callback is provided it will be called with a dict:
    { units_total, units_done, lessons_total, lessons_done, percent, elapsed_seconds, est_seconds_remaining }
    """

    context = "Class name: " + class_name

    # Helper to safely extract a string name from model output (which may be a dict)
    def _extract_name(item, keys=('unit_name','lesson_name','name','title')):
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for k in keys:
                if k in item and isinstance(item[k], str):
                    return item[k]
            # fall back to first string value in dict
            for v in item.values():
                if isinstance(v, str):
                    return v
            # last resort: JSON-serialize simple types
            try:
                return json.dumps(item)
            except Exception:
                return str(item)
        # fallback for other types
        return str(item)

    # Phase 1: get units and lessons names so we know total work
    units_json = message_to_json(ask_json("Create a json file with an array containing the unit names for a college class called " + class_name + ". The format for the name of each unit should be \"Unit X: [Unit Name]\". The json file should be in the format {\"units\": [array of unit names]}. Please respond with only the json file and nothing else. Do not reply with a question."))
    # normalize to a list: accept either {"units": [...]} or a top-level array
    if isinstance(units_json, dict):
        units_list = units_json.get('units') or []
    elif isinstance(units_json, list):
        units_list = units_json
    else:
        units_list = []

    output_class = full_class(class_name)

    unit_entries = []  # list of (unit_name, [lesson_names])
    for raw_unit in units_list:
        unit_name = _extract_name(raw_unit)
        # ask for lesson names for this unit
        lessons_json = message_to_json(ask_json("Please create a json file with an array containing the lesson names for a college class unit called " + unit_name + ". The format for the name of each lesson should be Lesson X: [Lesson Name]. The json file should be in the format {\"lessons\": [array of lesson names]}. Please respond with only the json file and nothing else. Here is the context you have generated so far: " + context))
        if isinstance(lessons_json, dict):
            raw_lessons = lessons_json.get('lessons') or []
        elif isinstance(lessons_json, list):
            raw_lessons = lessons_json
        else:
            raw_lessons = []
        # normalize lesson names to strings
        lesson_names = []
        for it in raw_lessons:
            lesson_names.append(_extract_name(it))
        context+= "\nUnit: " + unit_name + " Lessons: " + ", ".join(lesson_names)
        unit_entries.append((unit_name, lesson_names))

    units_total = len(unit_entries)
    lessons_total = sum(len(lns) for _, lns in unit_entries)
    total_steps = units_total + lessons_total if (units_total + lessons_total) > 0 else 1

    start_time = time.time()
    units_done = 0
    lessons_done = 0

    # Helper to call progress callback
    def _report():
        if not progress_callback:
            return
        elapsed = time.time() - start_time
        completed = units_done + lessons_done
        percent = int((completed / total_steps) * 100)
        remaining_steps = max(total_steps - completed, 0)
        rate = (elapsed / completed) if completed > 0 else None
        est_remaining = int(rate * remaining_steps) if rate else None
        progress_callback({
            'units_total': units_total,
            'units_done': units_done,
            'lessons_total': lessons_total,
            'lessons_done': lessons_done,
            'percent': percent,
            'elapsed_seconds': int(elapsed),
            'est_seconds_remaining': est_remaining
        })

    # Phase 2: generate unit/lesson content
    for unit_name, lesson_names in unit_entries:
        new_unit = unit(unit_name)
        units_done += 1
        _report()
        for lesson_name in lesson_names:
            content = ask_question(input="Please create the content for a college class lesson called " + lesson_name + ". The content should be in markdown format and should include headings, subheadings, bullet points, and code snippets where appropriate. Please respond with only the markdown content and nothing else. Do not provide example or filler content. You are speaking directly to a student. Here is context you have generated so far: " + context)
            context+= "\nUnit: " + unit_name + " Lesson: " + lesson_name + "\nContent: " + summarize(content)
            new_lesson = lesson(lesson_name, content)
            practice_problems_response = ask_question(input="Please practice problems and their solutions for a college class lesson called " + lesson_name + " in a unit called " + unit_name + ". Start each question with Q: and each answer with A: ")
            practice_problems = parse_qa(practice_problems_response)
            for problem in practice_problems:
                new_problem = practice_problem(problem[0], problem[1])
                new_lesson.practiceProblems.append(new_problem)
            new_unit.lessons.append(new_lesson)
            lessons_done += 1
            _report()
        output_class.units.append(new_unit)

    # final report
    if progress_callback:
        _report()
    return output_class

def ask_question(input: str, useMarkdown: bool = True, model_name: str = None) -> str:
    """Ask a question to the model, optionally requesting markdown output."""

    model = model_name or os.getenv('OLLAMA_MODEL', 'llama3')
    # System message should be a short role instruction; user holds the task
    system_msg = "You are an assistant that responds helpfully." if useMarkdown else "You are an assistant that responds helpfully."
    user_msg = input
    if useMarkdown:
        user_msg += "\n\nPlease answer in markdown format."

    response = ollama.chat(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ],
        options={
            # keep defaults low for deterministic output when needed; adjust at call-site
            "temperature": 0.0,
            "top_p": 0.0,
            "top_k": 50,
            "seed": random.randint(1, 1_000_000)
        }
    )

    return response["message"]["content"]


def ask_json(prompt: str, model_name: str = None, max_attempts: int = 2) -> str:
    """Ask the model to return JSON only. Retries once with an explicit repair instruction if parsing fails."""
    model = model_name or os.getenv('OLLAMA_MODEL', 'llama3')
    system = "You are a strict JSON generator. Output only valid JSON and nothing else. If you cannot, output a single JSON object like {\"error\":\"explain why\"} and nothing else."
    user = prompt
    for attempt in range(max_attempts):
        resp = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            options={
                "temperature": 0.0,
                "top_p": 0.0,
                "max_tokens": 1500,
            }
        )
        text = resp["message"]["content"]
        # quick JSON detection
        if text.strip().startswith('{') or text.strip().startswith('['):
            return text
        # otherwise ask the model to repair into JSON-only
        user = "Please output only valid JSON. Fix the following output to be valid JSON only:\n" + text
    return text

def summarize(input: str) -> str:
    return ask_question(input="Please provide a concise summary of the following text for context in future questions. Text: " + input + ". Your response should be a few sentences long.", useMarkdown=False)


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
    # Try to extract a JSON-like substring robustly (handles code fences and stray text)
    import re

    # Look for a JSON object/array anywhere in the message
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", message)
    candidate = None
    if m:
        candidate = m.group(1)
    else:
        # Try fenced code block with optional json hint
        m2 = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", message)
        if m2:
            candidate = m2.group(1)

    # If still no candidate, attempt a repair pass via the model
    if not candidate:
        print("No JSON found in message; attempting to repair. Raw message:\n", message)
        # write raw message to logs for inspection
        try:
            os.makedirs('logs', exist_ok=True)
            with open(os.path.join('logs', f'json_fail_raw_{int(time.time())}.txt'), 'w', encoding='utf-8') as lf:
                lf.write(message)
        except Exception:
            pass
        try:
            revised = _revise_json_str(message, "No JSON found in message")
            # save revised attempt too
            try:
                with open(os.path.join('logs', f'json_fail_revised_{int(time.time())}.txt'), 'w', encoding='utf-8') as lf:
                    lf.write(revised)
            except Exception:
                pass
            m3 = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", revised)
            if m3:
                candidate = m3.group(1)
            else:
                print("No JSON found after repair attempt. Returning empty dict.")
                return {}
        except Exception as e:
            print("Repair attempt failed:", e)
            return {}

    # Now try parsing the candidate with a few repair attempts
    max_attempts = 3
    attempt = 0
    last_result = candidate
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