async function analyzeDocument(file) {
    const endpoint = "https://tmhna-hrs-doc-poc-ai.cognitiveservices.azure.com/";
    const key = "5696497f8e8c423b9350c2eae32be3bb";
    const modelId = "Model3.1";

    try {
        // Convert the file to a binary stream for Azure API
        const formData = new FormData();
        formData.append("file", file);

        // Begin analysis
        const pollerResponse = await fetch(`${endpoint}/formrecognizer/v2.1/custom/models/${modelId}/analyze`, {
            method: "POST",
            headers: {
                "Ocp-Apim-Subscription-Key": key
            },
            body: formData
        });

        if (!pollerResponse.ok) {
            throw new Error(`Error starting analysis: ${pollerResponse.statusText}`);
        }

        const pollerUrl = pollerResponse.headers.get("operation-location");

        // Poll for results
        let analysisResult;
        while (true) {
            const pollResponse = await fetch(pollerUrl, {
                headers: { "Ocp-Apim-Subscription-Key": key }
            });
            const pollResult = await pollResponse.json();

            if (pollResult.status === "succeeded") {
                analysisResult = pollResult.analyzeResult;
                break;
            } else if (pollResult.status === "failed") {
                throw new Error("Document analysis failed.");
            }

            // Wait before polling again
            await new Promise(resolve => setTimeout(resolve, 2000));
        }

        // Process the results
        return processAnalysisResult(analysisResult);

    } catch (error) {
        console.error("Error analyzing document:", error);
        alert("Failed to analyze document. Please try again.");
    }
}

function processAnalysisResult(result) {
    const extractedData = {};
    const warnings = [];
    const deductions = [];
    let score = 10;

    for (const document of result.documents) {
        // Extract fields
        for (const [name, field] of Object.entries(document.fields)) {
            const content = field.value || field.content || "None";
            const confidence = field.confidence || "N/A";

            extractedData[name] = { content, confidence };

            if (confidence !== "N/A" && confidence < 0.5) {
                warnings.push(`${name}'s confidence is low (${confidence.toFixed(2)}). Manual check may be needed.`);
            }
        }

        // Calculate score (simplified from Python logic)
        const requiredFields = ["Title", "Vendor", "Start Date", "End Date", "Final Amount Requested"];
        for (const field of requiredFields) {
            if (!extractedData[field] || extractedData[field].content === "None") {
                deductions.push(`1 point deducted for missing ${field}.`);
                score -= 1;
            }
        }

        extractedData.Score = score;
    }

    return { extractedData, warnings, deductions, summary: JSON.stringify(extractedData, null, 2) };
}
