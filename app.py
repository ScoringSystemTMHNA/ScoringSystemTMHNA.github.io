import pandas as pd
from flask import Flask, request, jsonify, Response, redirect, url_for
import time
import re
import matplotlib
import matplotlib.pyplot as plt
from io import StringIO
import os
import csv
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

# Azure configuration
endpoint = "https://tmhna-hrs-doc-poc-ai.cognitiveservices.azure.com/"
key = "5696497f8e8c423b9350c2eae32be3bb"
model_id = "Model3.1"

# Create a DocumentAnalysisClient
document_analysis_client = DocumentAnalysisClient(endpoint=endpoint, credential=AzureKeyCredential(key))

def analyze_document(file_path):
    csv_file_path = "testtt.csv"

    # Prepare to collect data for CSV
    csv_data = []
    fields_headers = set()  # A set to collect all unique headers for CSV

    # String to accumulate the results
    output_string = ""

    # Dictionary to store extracted data for return
    extracted_data = {}
    warning_messages = []
    deduction_messages = []

    # Open the file and analyze it
    with open(file_path, "rb") as file:
        poller = document_analysis_client.begin_analyze_document(model_id=model_id, document=file)
        result = poller.result()

    # Process each document in the result
    for document in result.documents:
        # Collect fields in the required format for the single file
        fields_data = {"document_name": file_path}  # Use file_path instead of `document_name`
        output_string += f"The document name is {file_path}\n"
        extracted_data["Document Name"] = {"content": file_path, "confidence": None}  # Add document name

        # Initial score
        score = 10
        
        # Extract field contents
        extracted_fields = {
            "Title": None,
            "Vendor": None,
            "Start Date": None,
            "End Date": None,
            "Final Amount Requested": None,
            "Payment Schedule": None,
            "Vendor SOW": None,
            "CCR": None,
            "increase_by": None,
            "increase_from": None,
            "decrease_by": None,
            "new_end_date": None
        }

        # Extract fields and append them to the string
        for name, field in document.fields.items():
            field_content = field.value if field.value else field.content
            confidence = field.confidence
            fields_data[f"{name}_content"] = field_content
            fields_data[f"{name}_confidence"] = confidence
            fields_headers.add(f"{name}_content")
            fields_headers.add(f"{name}_confidence")

            # Store extracted fields for summary check
            if name in extracted_fields:
                extracted_fields[name] = field_content
            
            # Append field content to the extracted_data dictionary
            # Append field content to the extracted_data dictionary
            if name != "Payment Schedule" and name != "Payment Schedule Extended":
                extracted_data[name] = {
                    "content": field_content if field_content else "None",
                    "confidence": confidence if confidence else "N/A"
                }
                if confidence is not None and confidence < 0.5:
                    warning_messages.append(f"{name}'s confidence level is low ({confidence:.2f}), manual check may be needed.")

            # Special handling for "Payment Schedule" field
            if name == "Payment Schedule" and isinstance(field_content, list):
                contains_milestone = any("Payment Milestone Trigger" in str(item) for item in field_content)
                contains_invoice_date = any("Estimated Invoice Date" in str(item) for item in field_content)
                contains_fee = any("Fee" in str(item) for item in field_content)

                # Initialize Payment Schedule entry if not already present
                if "Payment Schedule" not in extracted_data:
                    extracted_data["Payment Schedule"] = {
                        "content": [],
                        "confidence": "N/A"  # Default confidence, can be updated as needed
                    }

                # Append matching keywords to Payment Schedule
                if contains_milestone:
                    extracted_data["Payment Schedule"]["content"].append("Payment Milestone Trigger")
                if contains_invoice_date:
                    extracted_data["Payment Schedule"]["content"].append("Estimated Invoice Date")
                if contains_fee:
                    extracted_data["Payment Schedule"]["content"].append("Fee")

                # Append keyword checks to the string
                output_string += f"Payment Schedule {'contains' if contains_milestone else 'does not contain'} 'Payment Milestone Trigger'\n"
                output_string += f"Payment Schedule {'contains' if contains_invoice_date else 'does not contain'} 'Estimated Invoice Date'\n"
                output_string += f"Payment Schedule {'contains' if contains_fee else 'does not contain'} 'Fee'\n"

            elif name == "Payment Schedule Extended" and isinstance(field_content, list):
                contains_milestone = any("Payment Milestone Trigger" in str(item) for item in field_content)
                contains_invoice_date = any("Estimated Invoice Date" in str(item) for item in field_content)
                contains_fee = any("Fee" in str(item) for item in field_content)

                # Initialize Payment Schedule entry if not already present
                if "Payment Schedule Extended" not in extracted_data:
                    extracted_data["Payment Schedule Extended"] = {
                        "content": [],
                        "confidence": "N/A"  # Default confidence, can be updated as needed
                    }

                # Append matching keywords to Payment Schedule
                if contains_milestone:
                    extracted_data["Payment Schedule Extended"]["content"].append("Payment Milestone Trigger")
                if contains_invoice_date:
                    extracted_data["Payment Schedule Extended"]["content"].append("Estimated Invoice Date")
                if contains_fee:
                    extracted_data["Payment Schedule Extended"]["content"].append("Fee")

                # Append keyword checks to the string
                output_string += f"Payment Schedule Extended {'contains' if contains_milestone else 'does not contain'} 'Payment Milestone Trigger'\n"
                output_string += f"Payment Schedule Extended {'contains' if contains_invoice_date else 'does not contain'} 'Estimated Invoice Date'\n"
                output_string += f"Payment Schedule Extended {'contains' if contains_fee else 'does not contain'} 'Fee'\n"
                
            elif name == "Sections" and isinstance(field_content, list):
                sections = []
                for item in field_content:
                    item_str = str(item)
                    if "value='" in item_str:
                        start_idx = item_str.find("value='") + len("value='")
                        end_idx = item_str.find("'", start_idx)
                        section_title = item_str[start_idx:end_idx].strip()
                        sections.append(section_title)
                output_string += f"The document contains the following sections: {', '.join(sections)}\n"
                extracted_data["Sections"] = {
                    "content": ', '.join(sections),
                    "confidence": None
                }
            else:
                output_string += f"{name} is extracted as '{field_content}', with a confidence level of {confidence}\n"
        
        csv_data.append(fields_data)  # Append data for the file

        # Summary output
        output_string += "\n--- Summary ---\n"
        
        # Check required fields and adjust score
        if extracted_fields["CCR"]:
            # Document is a contract change request
            output_string += "The file is a contract change request.\n"
            extracted_data["Document Type"] = "CCR"
            
            # Deduct 1 points for each missing core field
            for field_name in ["Title", "Vendor", "Start Date", "End Date", "Final Amount Requested", "Payment Schedule", "Vendor SOW"]:
                if extracted_fields[field_name] and extracted_fields[field_name] != "None":
                    output_string += f"{field_name} is present.\n"
                else:
                    output_string += f"{field_name} is empty/missing.\n"
                    deduction_messages.append(f"1 point is deducted because {field_name} is missing.")
                    score -= 1
            
            # Add 1 point for each additional field that is present
            for field_name in ["increase_by", "increase_from", "decrease_by", "new_end_date"]:
                if extracted_fields[field_name]:
                    output_string += f"{field_name} is present.\n"
                else:
                    output_string += f"{field_name} is empty/missing.\n"
                    deduction_messages.append(f"0.25 point is deducted because {field_name} is missing.")
                    score -= 0.25
        else:
            # Document is a regular SOW
            output_string += "The file is a regular SOW.\n"
            extracted_data["Document Type"] = "SOW"
            
            # Deduct 1 point for each missing core field
            for field_name in ["Title", "Vendor", "Start Date", "End Date", "Final Amount Requested", "Payment Schedule", "Vendor SOW"]:
                if field_name != "Payment Schedule":
                    if extracted_fields[field_name] and extracted_fields[field_name] != "None":
                        output_string += f"{field_name} is present.\n"
                    else:
                        output_string += f"{field_name} is empty/missing.\n"
                        deduction_messages.append(f"1 point is deducted because {field_name} is missing.")
                        score -= 1
                else:
                    if extracted_fields[field_name]:
                        output_string += f"{field_name} is present.\n"
                    else:
                        output_string += f"{field_name} is empty/missing.\n"
                        deduction_messages.append(f"2 point is deducted because {field_name} is missing.")
                        score -= 2
            
            # Deduct 2 points for each additional field that is present
            for field_name in ["increase_by", "increase_from", "decrease_by", "new_end_date"]:
                if extracted_fields[field_name]:
                    output_string += f"{field_name} is present.\n"
                else:
                    output_string += f"{field_name} is empty/missing.\n"

        # Ensure score does not go below 0
        # score = max(0, score)
        output_string += f"\nFinal Score: {score} out of 10\n"
        extracted_data["Score"] = score

    # Write to CSV file with dynamic headers
    fieldnames = ["document_name"] + sorted(fields_headers)  # Sort headers for consistency
    with open(csv_file_path, mode="w", newline='', encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in csv_data:
            writer.writerow(row)

#     output_string += f"Data for the file '{file_path}' has been written to {csv_file_path}\n"

#     return extracted_data  # Return the dictionary

    extracted_data["Warnings"] = warning_messages  # Add warnings to extracted data
    extracted_data["Deductions"] = deduction_messages
    extracted_data["Summary"] = output_string.split("\n--- Summary ---\n")[1] if "--- Summary ---" in output_string else ""
    return extracted_data



app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure the upload folder exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.route('/')
def home():
    with open("index.html") as f:
        html = f.read()
    return html

# @app.route('/upload', methods=['POST'])
# def upload_file():
#     if 'file' not in request.files:
#         return "No file part in the request"
#     file = request.files['file']
#     if file.filename == '':
#         return "No selected file"
#     if file:
#         file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
#         file.save(file_path)
#         # return f"{file.filename} is uploaded successfully!"
#         output_string = analyze_document(file_path)
#         return f"<pre>{output_string}</pre>"
#     return "File upload failed"

# @app.route('/upload', methods=['POST'])
# def upload_file():
#     if 'file' not in request.files:
#         return jsonify({"error": "No file part in the request"}), 400
#     file = request.files['file']
#     if file.filename == '':
#         return jsonify({"error": "No selected file"}), 400
#     if file:
#         file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
#         file.save(file_path)
        
#         # Call the analyze_document function and prepare the result for the frontend
#         extracted_data = analyze_document(file_path)
#         return jsonify(extracted_data)

#     return jsonify({"error": "File upload failed"}), 500

# @app.route('/upload', methods=['POST'])
# def upload_file():
#     if 'file' not in request.files:
#         return jsonify({"error": "No file part in the request"}), 400
#     file = request.files['file']
#     if file.filename == '':
#         return jsonify({"error": "No selected file"}), 400
#     if file:
#         file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
#         file.save(file_path)
        
#         # Call the analyze_document function and prepare the result for the frontend
#         extracted_data = analyze_document(file_path)

#         # Extract the summary from the analyze_document output
#         summary = extracted_data.pop("Summary", "")  # Remove summary from the main data

#         return jsonify({"fields": extracted_data, "summary": summary})

#     return jsonify({"error": "File upload failed"}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        try:
            file.save(file_path)
        except Exception as e:
            print(f"Error saving file: {e}")
            return jsonify({"error": "Failed to save the uploaded file"}), 500
        
        try:
            # Call the analyze_document function
            extracted_data = analyze_document(file_path)

            # Extract the summary from the analyze_document output
            summary = extracted_data.pop("Summary", "")  # Remove summary from the main data

            # Debugging: Print extracted_data and summary to identify non-serializable objects
            print("Extracted Data:", extracted_data)
            print("Summary:", summary)

            # Ensure all objects are serializable
            for key, value in extracted_data.items():
                try:
                    # Attempt to serialize each value to JSON
                    json_test = jsonify({key: value})
                except Exception as e:
                    print(f"Serialization error for key '{key}' with value '{value}': {e}")
                    raise e

            return jsonify({"fields": extracted_data, "summary": summary})

        except Exception as e:
            # Log detailed error information
            print(f"Error during document analysis: {e}")
            return jsonify({"error": f"Internal server error: {str(e)}"}), 500

    return jsonify({"error": "File upload failed"}), 500



if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=True, threaded=False)  # don't change this line!
