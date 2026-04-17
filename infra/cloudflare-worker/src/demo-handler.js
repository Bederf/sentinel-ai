/**
 * Demo Request Handler
 * Handles form submissions from sentinel-ai.co.za landing page
 * Sends email notifications via Resend (no database required)
 */

// Allowed origins for CORS
const ALLOWED_ORIGINS = [
  "https://sentinel-ai.co.za",
  "https://app.aimthelaw.co.za",
  "https://api.aimthelaw.co.za",
  "http://localhost:5173",
  "http://127.0.0.1:5173",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
];

function getCorsHeaders(origin) {
  const isAllowed = ALLOWED_ORIGINS.includes(origin);
  return {
    "Access-Control-Allow-Origin": isAllowed ? origin : "null",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-CSRF-Token, X-Requested-With",
    "Access-Control-Allow-Credentials": isAllowed ? "true" : "false",
  };
}

export async function handleDemoRequest(request, env) {
  const origin = request.headers.get("Origin") || "";
  const corsHeaders = getCorsHeaders(origin);

  // Handle CORS preflight
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: corsHeaders
    });
  }

  // Only accept POST
  if (request.method !== "POST") {
    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json", ...corsHeaders } }
    );
  }

  try {
    const data = await request.json();
    const { name, company, email, phone, message } = data;

    // Validation - only email is required
    if (!email) {
      return new Response(
        JSON.stringify({ error: "Email is required" }),
        { status: 400, headers: { "Content-Type": "application/json", ...corsHeaders } }
      );
    }

    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      return new Response(
        JSON.stringify({ error: "Invalid email address" }),
        { status: 400, headers: { "Content-Type": "application/json", ...corsHeaders } }
      );
    }

    // Check if RESEND_API_KEY is configured
    console.log(`RESEND_API_KEY present: ${env.RESEND_API_KEY ? "yes" : "no"}`);
    console.log(`OWNER_EMAIL: ${env.OWNER_EMAIL}`);

    if (!env.RESEND_API_KEY) {
      return new Response(
        JSON.stringify({ error: "Email service not configured (missing RESEND_API_KEY)" }),
        { status: 500, headers: { "Content-Type": "application/json", ...corsHeaders } }
      );
    }

    // Send email notification
    try {
      console.log("Attempting to send email via Resend...");
      const emailPayload = {
        from: "onboarding@resend.dev",
        to: env.OWNER_EMAIL || "admin@sentinel-ai.co.za",
        subject: `New Demo Request: ${company || "N/A"}`,
        html: `
          <h2>New Demo Request</h2>
          <p><strong>Name:</strong> ${name || "Not provided"}</p>
          <p><strong>Company:</strong> ${company || "Not provided"}</p>
          <p><strong>Email:</strong> ${email}</p>
          <p><strong>Phone:</strong> ${phone || "Not provided"}</p>
          <p><strong>Message:</strong> ${message || "No message"}</p>
          <hr>
          <p><em>Submitted: ${new Date().toLocaleString()}</em></p>
        `,
      };

      console.log(`Email recipient: ${emailPayload.to}`);
      console.log(`Resend API Key: ${env.RESEND_API_KEY.substring(0, 10)}...`);

      const emailResponse = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(emailPayload),
      });

      const responseText = await emailResponse.text();
      console.log(`Resend API status: ${emailResponse.status}`);
      console.log(`Resend API response: ${responseText}`);

      if (!emailResponse.ok) {
        console.error(`Resend error (${emailResponse.status}): ${responseText}`);
        return new Response(
          JSON.stringify({
            error: "Failed to send email",
            details: `Resend API returned ${emailResponse.status}: ${responseText}`
          }),
          { status: 500, headers: { "Content-Type": "application/json", ...corsHeaders } }
        );
      }

      return new Response(
        JSON.stringify({
          success: true,
          message: "Demo request received. We'll contact you soon!",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        }
      );

    } catch (emailErr) {
      console.error("Email fetch error:", emailErr.message || emailErr);
      return new Response(
        JSON.stringify({
          error: "Email service error",
          details: emailErr.message
        }),
        { status: 500, headers: { "Content-Type": "application/json", ...corsHeaders } }
      );
    }

  } catch (error) {
    console.error("Demo handler error:", error);
    return new Response(
      JSON.stringify({ error: error.message || "Internal server error" }),
      {
        status: 500,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      }
    );
  }
}
