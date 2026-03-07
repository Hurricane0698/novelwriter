export interface Novel {
  id: number
  title: string
  author: string
  file_path: string
  total_chapters: number
  created_at: string
  updated_at: string
}

export interface Chapter {
  id: number
  novel_id: number
  chapter_number: number
  title: string
  content: string
  created_at: string
}
