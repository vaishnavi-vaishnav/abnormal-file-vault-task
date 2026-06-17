import axios from 'axios';
import { File as FileType } from '../types/file';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

export const fileService = {
  async uploadFile(file: File): Promise<FileType> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await axios.post(`${API_URL}/files/`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  async getFiles(params?: Record<string, any>): Promise<FileType[]> {
    const response = await axios.get(`${API_URL}/files/`, { params });
    return response.data;
  },

  async getFileTypes(): Promise<string[]> {
    const response = await axios.get(`${API_URL}/files/file_types/`);
    return response.data.file_types || [];
  },

  async deleteFile(id: string): Promise<void> {
    await axios.delete(`${API_URL}/files/${id}/`);
  },

  async getFile(id: string): Promise<FileType> {
    const response = await axios.get(`${API_URL}/files/${id}/`);
    return response.data;
  },

  async fetchFileBlob(fileUrl: string): Promise<Blob> {
    const response = await axios.get(fileUrl, {
      responseType: 'blob',
    });
    return response.data;
  },

  async downloadFile(fileUrl: string, filename: string): Promise<void> {
    try {
      const response = await axios.get(fileUrl, {
        responseType: 'blob',
      });
      
      // Create a blob URL and trigger download
      const blob = new Blob([response.data]);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Download error:', error);
      throw new Error('Failed to download file');
    }
  },
}; 