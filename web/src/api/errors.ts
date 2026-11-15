import type { HttpErrorBody } from "../protocol/types";

export type EntryField = "display_name" | "seat" | "code" | "form";

export interface FieldError {
  field: EntryField;
  message: string;
}

const GENERIC_MESSAGE = "Something went wrong. Please try again.";

/** Maps an ADR 0009 §4 HTTP error body to the entry form field it concerns. */
export function mapHttpError(body: HttpErrorBody): FieldError {
  const { code, field, message } = body.error;
  switch (code) {
    case "VALIDATION_FAILED":
      if (field === "display_name" || field === "seat") return { field, message };
      return { field: "form", message };
    case "TABLE_NOT_FOUND":
      return { field: "code", message: "This code doesn't match any open table." };
    case "DISPLAY_NAME_TAKEN":
      return { field: "display_name", message };
    case "SEAT_TAKEN":
      return { field: "seat", message };
    case "INVALID_SEAT":
      return { field: "seat", message };
    case "ALREADY_MEMBER":
    case "LEFT_TABLE":
    case "INTERNAL_ERROR":
      return { field: "form", message: message || GENERIC_MESSAGE };
  }
}
