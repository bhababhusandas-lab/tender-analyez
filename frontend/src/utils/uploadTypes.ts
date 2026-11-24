// File types the backend can read (see backend/app/core/document_convert.py).
// Old Word/OpenDocument/RTF/PowerPoint files are converted on the server,
// scans and photos are read by OCR, and archives are expanded.
const DOCUMENTS = '.pdf,.doc,.docx,.rtf,.odt,.wps,.xlsx,.xls,.ods,.ppt,.pptx,.odp,.txt,.md,.csv'
const IMAGES = '.jpg,.jpeg,.png,.tif,.tiff,.bmp,.webp'

/** Tender uploads (analysis, roadmap, re-analysis): documents, images and archives. */
export const TENDER_UPLOAD_ACCEPT = `${DOCUMENTS},${IMAGES},.zip,.rar,.7z`
export const TENDER_UPLOAD_HINT =
  'Select up to 10 files: PDF (including scans), Word, Excel, PowerPoint, OpenDocument, RTF, images, TXT/CSV, or ZIP/RAR/7Z'

/** Chat attachments are read one by one, so archives are not expanded there. */
export const CHAT_UPLOAD_ACCEPT = `${DOCUMENTS},${IMAGES}`
