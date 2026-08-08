/* 입주민 관리 API 계약 (/api/residents).
   analyticsContracts 처럼 도메인 단위로 파일을 나눈다 — contracts.ts 가 이미 충분히 크다. */

export type ResidentListItemResponse = {
  residentId: number
  name: string
  /** 목록에서는 서버가 가운데 자리를 가려서 내려준다 */
  maskedPhoneNumber: string
  buildingNumber: string
  unitNumber: string
  vehicleCount: number
  representativeLicensePlate: string | null
  notificationEnabled: boolean
  lastNotifiedAt: string | null
}

export type ResidentListPageResponse = {
  content: ResidentListItemResponse[]
  page: number
  size: number
  totalElements: number
  totalPages: number
  first: boolean
  last: boolean
}

export type ResidentFilterOptionsResponse = {
  buildingNumbers: string[]
}

export type RegisteredVehicleResponse = {
  vehicleId: number
  licensePlate: string
  disabledVehicle: boolean
}

export type ResidentNotificationHistoryResponse = {
  notificationId: number
  eventId: number
  eventType: string
  status: string
  sentAt: string | null
  createdAt: string
}

export type ResidentDetailResponse = {
  residentId: number
  name: string
  /** 상세에서는 전체 번호 */
  phoneNumber: string
  buildingNumber: string
  unitNumber: string
  notificationEnabled: boolean
  vehicles: RegisteredVehicleResponse[]
  notificationCount: number
  violationCount: number
  recentNotifications: ResidentNotificationHistoryResponse[]
  createdAt: string
  updatedAt: string
}

export type ResidentSummaryResponse = {
  residentId: number
  name: string
  phoneNumber: string
  buildingNumber: string
  unitNumber: string
  notificationEnabled: boolean
  updatedAt: string
}

export type VehicleRegisterRequest = {
  licensePlate: string
  disabledVehicle: boolean
}

export type ResidentRegisterRequest = {
  name: string
  phoneNumber: string
  buildingNumber: string
  unitNumber: string
  vehicles?: VehicleRegisterRequest[]
}

export type ResidentUpdateRequest = {
  name: string
  phoneNumber: string
  buildingNumber: string
  unitNumber: string
}

export type ResidentNotificationUpdateRequest = {
  notificationEnabled: boolean
}

export type ResidentListRequest = {
  keyword?: string
  buildingNumber?: string
  notificationEnabled?: boolean
  page?: number
  size?: number
  sort?: string[]
}
