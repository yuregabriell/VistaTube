package com.github.libretube.ui.preferences

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts

/**
 * Optional Vista ID local linking. Does not alter LibreTube's existing
 * preferences, subscriptions, playlists, viewing history or offline memory.
 */
class VistaIdAccountActivity : ComponentActivity() {
    private val prefs by lazy { getSharedPreferences("vista_id_link", Context.MODE_PRIVATE) }
    private val link = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val id = result.data?.getStringExtra("com.vista.id.profile_id")
        val name = result.data?.getStringExtra("com.vista.id.profile_name")
        val mode = result.data?.getStringExtra("com.vista.id.mode")
        if (result.resultCode == Activity.RESULT_OK &&
            id != null && id.matches(Regex("V[A-Z2-9]{12}")) && mode == "local") {
            prefs.edit().putString("id", id).putString("name", name?.take(48) ?: "").apply()
            render()
        } else if (result.resultCode == Activity.RESULT_OK) {
            Toast.makeText(this, "Resposta Vista ID inválida", Toast.LENGTH_LONG).show()
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        render()
    }
    private fun dp(n: Int) = (n * resources.displayMetrics.density + .5f).toInt()
    private fun render() {
        val id = prefs.getString("id", null)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(13,17,29))
            setPadding(dp(24),dp(28),dp(24),dp(28))
        }
        fun text(t: String, size: Float) {
            layout.addView(TextView(this).apply {
                text = t; textSize = size; setTextColor(Color.WHITE)
                setPadding(0,dp(9),0,dp(9))
            })
        }
        text("Vista ID · opcional",25f)
        if (id == null) text("Continua sem conta, ou associa o teu perfil local Vista ID.",15f)
        else text("Ligado localmente: ${prefs.getString("name","")} · $id",16f)
        text("O histórico, subscrições, playlists e preferências atuais permanecem no VistaTube. Ainda não há sincronização cloud.",13f)
        layout.addView(Button(this).apply {
            text = if(id == null) "Ligar Vista ID" else "Alterar Vista ID"
            setOnClickListener {
                try {
                    link.launch(Intent("com.vista.id.action.LINK_LOCAL_PROFILE").setPackage("com.vista.id"))
                } catch (_: ActivityNotFoundException) {
                    Toast.makeText(this@VistaIdAccountActivity, "Instala o Vista ID v0.2 ou superior.", Toast.LENGTH_LONG).show()
                } catch (e: Exception) {
                    Toast.makeText(this@VistaIdAccountActivity, "Não foi possível abrir Vista ID: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        })
        if (id != null) layout.addView(Button(this).apply {
            text = "Desligar, sem apagar dados"
            setOnClickListener { prefs.edit().clear().apply(); render() }
        })
        layout.addView(Button(this).apply { text = "Voltar"; setOnClickListener { finish() } })
        val scroll = android.widget.ScrollView(this)
        scroll.addView(layout)
        setContentView(scroll)
    }
}
