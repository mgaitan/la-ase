const editors = document.querySelectorAll("[data-markdown-editor]");

function wrapSelection(textarea, before, after = before, fallback = "") {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end) || fallback;
  const replacement = `${before}${selected}${after}`;
  textarea.setRangeText(replacement, start, end, "end");
  textarea.focus();
}

function prefixLines(textarea, prefix) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.slice(start, end);
  const source = selected || "Item";
  const replaced = source
    .split("\n")
    .map((line) => `${prefix}${line || " "}`.trimEnd())
    .join("\n");
  textarea.setRangeText(replaced, start, end, "end");
  textarea.focus();
}

async function renderPreview(editor, textarea) {
  const panel = editor.querySelector("[data-preview-panel]");
  const targetId = textarea.dataset.previewTarget;
  const target = document.getElementById(targetId);
  const formData = new FormData();
  formData.set("content", textarea.value);
  const response = await fetch("/admin/markdown/preview", {
    method: "POST",
    body: formData,
    credentials: "same-origin",
  });
  target.innerHTML = await response.text();
  panel.hidden = false;
  textarea.closest("label").hidden = true;
}

async function uploadImage(editor, textarea, file) {
  const formData = new FormData();
  formData.set("file", file);
  const response = await fetch("/admin/uploads/images", {
    method: "POST",
    body: formData,
    credentials: "same-origin",
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "No se pudo subir la imagen.");
  }
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.setRangeText(payload.markdown, start, end, "end");
  textarea.focus();
}

editors.forEach((editor) => {
  const textarea = editor.querySelector("[data-markdown-input]");
  const panel = editor.querySelector("[data-preview-panel]");
  const fieldWrap = textarea.closest("label");
  const imageInput = editor.querySelector("[data-image-input]");

  imageInput.addEventListener("change", async () => {
    const file = imageInput.files?.[0];
    if (!file) {
      return;
    }
    try {
      await uploadImage(editor, textarea, file);
    } catch (error) {
      window.alert(error.message || "No se pudo subir la imagen.");
    } finally {
      imageInput.value = "";
    }
  });

  editor.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) {
      return;
    }
    event.preventDefault();
    const action = button.dataset.action;

    if (action === "bold") wrapSelection(textarea, "**", "**", "texto");
    if (action === "italic") wrapSelection(textarea, "*", "*", "texto");
    if (action === "heading") wrapSelection(textarea, "## ", "", "Titulo");
    if (action === "quote") prefixLines(textarea, "> ");
    if (action === "list") prefixLines(textarea, "- ");
    if (action === "link") {
      const url = window.prompt("URL del enlace");
      if (url) wrapSelection(textarea, "[", `](${url})`, "texto");
    }
    if (action === "image-upload") imageInput.click();
    if (action === "preview") await renderPreview(editor, textarea);
    if (action === "edit") {
      panel.hidden = true;
      fieldWrap.hidden = false;
      textarea.focus();
    }
  });
});
