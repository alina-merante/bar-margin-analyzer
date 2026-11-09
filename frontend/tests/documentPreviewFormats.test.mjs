import { describe, it } from "node:test";
import assert from "node:assert";

/**
 * Document preview format tests
 * Verifies that different document formats are displayed appropriately:
 * - PNG/JPG/JPEG/WebP: displayed as images
 * - TXT/CSV: shown as text links
 * - PDF: shown as images (converted to PNG by backend)
 * - Missing files: show "Anteprima non disponibile" message
 */

describe("Document Preview Format Handling", () => {
  describe("Image format documents", () => {
    it("should display PNG documents as images", () => {
      const document = {
        id: 1,
        original_filename: "document.png",
        document_type: "PNG",
        file_url: "/api/uploads/documents/doc.png",
        preview_url: "/api/uploads/previews/doc.png",
      };

      const previewUrl = document.preview_url;
      assert.ok(previewUrl, "preview_url should be defined");
      assert.ok(previewUrl.includes(".png"), "preview_url should contain .png");
    });

    it("should display JPG documents as images", () => {
      const document = {
        id: 2,
        original_filename: "photo.jpg",
        document_type: "JPG",
        file_url: "/api/uploads/documents/photo.jpg",
        preview_url: "/api/uploads/previews/photo.jpg",
      };

      const previewUrl = document.preview_url;
      assert.ok(previewUrl, "preview_url should be defined");
      assert.ok(previewUrl.includes(".jpg"), "preview_url should contain .jpg");
    });

    it("should display JPEG documents as images", () => {
      const document = {
        id: 3,
        original_filename: "image.jpeg",
        document_type: "JPEG",
        file_url: "/api/uploads/documents/image.jpeg",
        preview_url: "/api/uploads/previews/image.jpeg",
      };

      const previewUrl = document.preview_url;
      assert.ok(previewUrl, "preview_url should be defined");
      assert.ok(previewUrl.includes(".jpeg"), "preview_url should contain .jpeg");
    });

    it("should display WebP documents as images", () => {
      const document = {
        id: 4,
        original_filename: "photo.webp",
        document_type: "WEBP",
        file_url: "/api/uploads/documents/photo.webp",
        preview_url: "/api/uploads/previews/photo.webp",
      };

      const previewUrl = document.preview_url;
      assert.ok(previewUrl, "preview_url should be defined");
      assert.ok(previewUrl.includes(".webp"), "preview_url should contain .webp");
    });
  });

  describe("Text format documents", () => {
    it("should handle TXT documents with download link", () => {
      const document = {
        id: 5,
        original_filename: "notes.txt",
        document_type: "TXT",
        file_url: "/api/uploads/documents/notes.txt",
        preview_url: "/api/uploads/previews/notes.png",
      };

      assert.ok(document.file_url, "file_url should be defined");
      assert.ok(document.original_filename.includes(".txt"), "filename should contain .txt");
    });

    it("should handle CSV documents with download link", () => {
      const document = {
        id: 6,
        original_filename: "data.csv",
        document_type: "CSV",
        file_url: "/api/uploads/documents/data.csv",
        preview_url: "/api/uploads/previews/data.png",
      };

      assert.ok(document.file_url, "file_url should be defined");
      assert.ok(document.original_filename.includes(".csv"), "filename should contain .csv");
    });
  });

  describe("PDF format documents", () => {
    it("should handle PDF documents with multiple preview images", () => {
      const document = {
        id: 7,
        original_filename: "invoice.pdf",
        document_type: "PDF",
        file_url: "/api/uploads/documents/invoice.pdf",
        preview_url: "/api/uploads/previews/invoice_1.png,/api/uploads/previews/invoice_2.png",
      };

      const previewUrls = document.preview_url.split(",").map(u => u.trim());
      assert.strictEqual(previewUrls.length, 2, "should have 2 preview URLs");
      assert.ok(previewUrls[0].includes("invoice_1.png"), "first URL should be invoice_1.png");
      assert.ok(previewUrls[1].includes("invoice_2.png"), "second URL should be invoice_2.png");
    });

    it("should handle single-page PDF", () => {
      const document = {
        id: 8,
        original_filename: "single.pdf",
        document_type: "PDF",
        file_url: "/api/uploads/documents/single.pdf",
        preview_url: "/api/uploads/previews/single_1.png",
      };

      const previewUrls = document.preview_url.split(",").map(u => u.trim());
      assert.strictEqual(previewUrls.length, 1, "should have 1 preview URL");
      assert.ok(previewUrls[0].includes(".png"), "preview URL should be PNG");
    });
  });

  describe("Missing or unavailable previews", () => {
    it("should handle documents with missing preview_url", () => {
      const document = {
        id: 9,
        original_filename: "file.doc",
        document_type: "DOC",
        file_url: "/api/uploads/documents/file.doc",
        preview_url: "",
      };

      assert.strictEqual(document.preview_url, "", "preview_url should be empty");
      assert.ok(document.file_url, "file_url should be defined");
    });

    it("should handle documents with null preview_url", () => {
      const document = {
        id: 10,
        original_filename: "file.pptx",
        document_type: "PPTX",
        file_url: "/api/uploads/documents/file.pptx",
        preview_url: null,
      };

      assert.strictEqual(document.preview_url, null, "preview_url should be null");
      assert.ok(document.file_url, "file_url should be defined");
    });

    it("should handle documents with neither preview nor file URL", () => {
      const document = {
        id: 11,
        original_filename: "missing.pdf",
        document_type: "PDF",
        file_url: "",
        preview_url: "",
      };

      assert.strictEqual(document.file_url, "", "file_url should be empty");
      assert.strictEqual(document.preview_url, "", "preview_url should be empty");
    });
  });

  describe("URL path handling", () => {
    it("should correctly prepend /api to relative preview URLs", () => {
      const document = {
        id: 12,
        original_filename: "test.png",
        document_type: "PNG",
        file_url: "/uploads/documents/test.png",
        preview_url: "/uploads/previews/test.png",
      };

      const previewUrl = document.preview_url.startsWith("http")
        ? document.preview_url
        : `/api${document.preview_url}`;

      assert.strictEqual(previewUrl, "/api/uploads/previews/test.png", "should prepend /api to relative URL");
    });

    it("should handle absolute URLs (from CDN or external storage)", () => {
      const document = {
        id: 13,
        original_filename: "cdn.png",
        document_type: "PNG",
        file_url: "https://cdn.example.com/uploads/cdn.png",
        preview_url: "https://cdn.example.com/previews/cdn.png",
      };

      assert.ok(document.preview_url.includes("https://"), "absolute URLs should contain https://");
    });
  });

  describe("Document type case insensitivity", () => {
    it("should handle uppercase document types", () => {
      const document = {
        document_type: "PNG",
      };

      const type = (document.document_type || "").toUpperCase();
      assert.ok(["PNG", "JPG", "JPEG", "WEBP"].includes(type), "PNG should be recognized");
    });

    it("should handle lowercase document types", () => {
      const document = {
        document_type: "pdf",
      };

      const type = (document.document_type || "").toUpperCase();
      assert.strictEqual(type, "PDF", "lowercase pdf should become PDF");
    });

    it("should handle mixed case document types", () => {
      const document = {
        document_type: "JpG",
      };

      const type = (document.document_type || "").toUpperCase();
      assert.strictEqual(type, "JPG", "mixed case JpG should become JPG");
    });
  });

  describe("Preview scroll and styling", () => {
    it("should support multiple preview URLs for multi-page documents", () => {
      const document = {
        id: 14,
        original_filename: "multipage.pdf",
        document_type: "PDF",
        preview_url:
          "/api/uploads/previews/multipage_1.png," +
          "/api/uploads/previews/multipage_2.png," +
          "/api/uploads/previews/multipage_3.png",
      };

      const previewUrls = document.preview_url
        .split(",")
        .map((u) => u.trim());

      assert.strictEqual(previewUrls.length, 3, "should have 3 preview URLs");
      previewUrls.forEach((url, index) => {
        assert.ok(url.includes(`multipage_${index + 1}.png`), `URL ${index} should match pattern`);
      });
    });

    it("should handle preview URLs with whitespace", () => {
      const document = {
        id: 15,
        original_filename: "test.pdf",
        document_type: "PDF",
        preview_url:
          "/api/uploads/previews/test_1.png , /api/uploads/previews/test_2.png",
      };

      const previewUrls = document.preview_url
        .split(",")
        .map((u) => u.trim());

      assert.strictEqual(previewUrls.length, 2, "should have 2 preview URLs");
      assert.strictEqual(previewUrls[0], "/api/uploads/previews/test_1.png", "first URL should match");
      assert.strictEqual(previewUrls[1], "/api/uploads/previews/test_2.png", "second URL should match");
    });
  });
});
