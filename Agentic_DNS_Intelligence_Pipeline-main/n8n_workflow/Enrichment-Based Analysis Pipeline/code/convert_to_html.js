/*
 * Extracted verbatim from n8n Code node: "Convert to HTML"
 * Source of execution remains the n8n workflow JSON.
 */
return items.map((item, index) => {

  var fullText = item.json.report_text || "";

  var domainRegex = /[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+/;
  var rawMatch = fullText.match(domainRegex);
  var domain = rawMatch ? rawMatch[0].toLowerCase() : "report_" + (index + 1);

  var timestamp = new Date().toLocaleString();
  var fullTextWithTimestamp = fullText + "\n\nReport Generated On: " + timestamp;

  var escaped = fullTextWithTimestamp
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  var html =
    "<html><head>" +

    "<meta http-equiv='Cache-Control' content='no-store, no-cache, must-revalidate, max-age=0'>" +
    "<meta http-equiv='Pragma' content='no-cache'>" +
    "<meta http-equiv='Expires' content='0'>" +

    "<meta charset='UTF-8'>" +
    "<title>DNS Intelligence Report — " + domain + "</title>" +
    "<style>" +
      "body{font-family:Arial,sans-serif;margin:0;padding:20px;background:#fafafa;color:#333}" +
      "pre{background:#f0f0f0;padding:15px;border-left:4px solid #0055aa;white-space:pre-wrap}" +
      ".back-btn{display:inline-block;margin-top:20px;padding:10px 15px;background:#0055aa;color:white;text-decoration:none;border-radius:5px}" +
      ".back-btn:hover{background:#003f7d}" +
      "footer{margin-top:40px;font-size:12px;color:#777;text-align:center}" +
    "</style></head><body>" +

    "<h1>DNS Intelligence Report — " + domain + "</h1>" +
    "<pre>" + escaped + "</pre>" +

    "<a class='back-btn' href='/reports/'>← Back to Reports</a>" +

    "<footer>" +
      "Generated automatically by the Agentic-AI DNS Intelligence Pipeline." +
    "</footer>" +

    "</body></html>";

  return {
    json: {},
    binary: {
      data: {
        data: Buffer.from(html).toString("base64"),
        mimeType: "text/html",
        fileName: domain + "_report.html"
      }
    }
  };
});

