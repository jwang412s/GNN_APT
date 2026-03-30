/*
 * Extracted verbatim from n8n Code node: "Normalizing"
 * Source of execution remains the n8n workflow JSON.
 */
return items.map(item => {
  
  let raw = "";

  // Gemini stores content inside candidates → content → parts → text
  const candidates = item.json.candidates || [];
  for (let i = 0; i < candidates.length; i++) {
    const parts = (candidates[i].content && candidates[i].content.parts) || [];
    for (let j = 0; j < parts.length; j++) {
      if (typeof parts[j].text === "string") {
        raw += parts[j].text + "\n\n";
      }
    }
  }

  return {
    json: {
      report_text: raw.trim()
    }
  };
});

