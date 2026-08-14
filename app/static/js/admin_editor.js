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

async function resizeImageForUpload(file) {
  const maxDimension = 1280;
  if (file.type === "image/gif") {
    return file;
  }

  const image = await createImageBitmap(file, { imageOrientation: "from-image" });
  if (Math.max(image.width, image.height) <= maxDimension) {
    image.close();
    return file;
  }

  const scale = maxDimension / Math.max(image.width, image.height);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(image.width * scale);
  canvas.height = Math.round(image.height * scale);
  canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
  image.close();

  const blob = await new Promise((resolve) => {
    canvas.toBlob(resolve, file.type === "image/png" ? "image/png" : file.type, 0.85);
  });
  if (!blob) {
    return file;
  }
  return new File([blob], file.name, { type: blob.type });
}

async function uploadImage(editor, textarea, file) {
  const uploadFile = await resizeImageForUpload(file);
  const formData = new FormData();
  formData.set("file", uploadFile);
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

  function openImagePicker() {
    if (typeof imageInput.showPicker === "function") {
      imageInput.showPicker();
      return;
    }
    imageInput.click();
  }

  imageInput.addEventListener("change", async () => {
    const file = imageInput.files?.[0];
    if (!file) {
      return;
    }
    try {
      await uploadImage(editor, textarea, file);
      if (!panel.hidden) {
        await renderPreview(editor, textarea);
      }
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
    if (action === "image-upload") openImagePicker();
    if (action === "preview") await renderPreview(editor, textarea);
    if (action === "edit") {
      panel.hidden = true;
      fieldWrap.hidden = false;
      textarea.focus();
    }
  });
});
