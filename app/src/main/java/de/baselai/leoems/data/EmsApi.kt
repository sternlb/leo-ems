package de.baselai.leoems.data

import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path

// Vertrag gegen die lokale API v1 des Backends (specs/02-specification.md §9.1).
// Auth: Bearer-Token aus den App-Einstellungen (docs/api-token-auth.md).

data class StatusDto(
    val modus: String?,
    val state: String?,
    val grund: String?,          // Klartext-Begründung (REQ-050)
    val laedt: Boolean?,
    val strom_a: Int?,
    val phasen: Int?,
    val ueberschuss_w: Int?,
    val soc_fahrzeug: Double?,
    val soc_batterie: Double?,
    val p_netz_w: Double?,
    val p_sungrow_w: Double?,
    val garantieladung: Boolean?,
    val entladesperre: Boolean?,
)

data class RuleDto(
    val id: Int?,
    val wochentage: List<Int>,   // 0=Mo … 6=So
    val abfahrtszeit: String,    // "HH:MM"
    val soc_min: Int,
    val aktiv: Boolean,
)

interface EmsApi {
    @GET("api/v1/status")
    suspend fun status(@Header("Authorization") bearer: String): StatusDto

    @GET("api/v1/rules")
    suspend fun rules(@Header("Authorization") bearer: String): List<RuleDto>

    @POST("api/v1/rules")
    suspend fun addRule(@Header("Authorization") bearer: String, @Body rule: RuleDto)

    @PUT("api/v1/rules/{id}")
    suspend fun updateRule(@Header("Authorization") bearer: String, @Path("id") id: Int, @Body rule: RuleDto)

    @DELETE("api/v1/rules/{id}")
    suspend fun deleteRule(@Header("Authorization") bearer: String, @Path("id") id: Int)

    companion object {
        // baseUrl z.B. "http://homeassistant.local:8099/" (mDNS) oder manuelle IP aus den Einstellungen.
        fun create(baseUrl: String): EmsApi =
            Retrofit.Builder()
                .baseUrl(baseUrl)
                .addConverterFactory(MoshiConverterFactory.create())
                .build()
                .create(EmsApi::class.java)
    }
}
