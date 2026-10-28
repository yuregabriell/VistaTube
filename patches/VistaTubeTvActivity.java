package com.github.libretube.ui.activities;

import android.app.Activity;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * 16:9 D-pad-friendly VistaTube start page. Video catalog, search, playback and
 * subscriptions remain handled by the real LibreTube engine, not a fake feed.
 */
public final class VistaTubeTvActivity extends Activity {
    private static final int BACKGROUND = 0xff0b1424;
    private static final int WHITE = 0xfff6faff;
    private static final int MUTED = 0xffbbcde3;
    private static final int CYAN = 0xff58ccff;
    private int dp(float n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private GradientDrawable panel(int color, boolean focused) {
        GradientDrawable d = new GradientDrawable(
            GradientDrawable.Orientation.TL_BR, new int[]{color,0xff10263a});
        d.setCornerRadius(dp(18));
        d.setStroke(dp(focused ? 3 : 1), focused ? CYAN : 0xff40566f);
        return d;
    }
    private TextView label(String text, float size, int color, boolean bold) {
        TextView v = new TextView(this);
        v.setText(text); v.setTextSize(size); v.setTextColor(color);
        if (bold) v.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        v.setMaxLines(2);
        return v;
    }
    private void pad(LinearLayout p, int height) {
        View v = new View(this); p.addView(v,new LinearLayout.LayoutParams(1,dp(height)));
    }
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BACKGROUND);
        getWindow().setNavigationBarColor(BACKGROUND);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BACKGROUND);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(48), dp(31), dp(48), dp(40));
        scroll.addView(root);
        setContentView(scroll);

        root.addView(label("VISTA TUBE  •  TV", 14, CYAN, true));
        pad(root, 9);
        root.addView(label("Os teus vídeos, na televisão", 33, WHITE, true));
        pad(root, 11);
        root.addView(label("Pesquisa, inscrições e histórico continuam ligados à biblioteca local do VistaTube. Navega com o comando da TV.", 15, MUTED, false));
        pad(root, 28);

        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        searchRow.setGravity(Gravity.CENTER_VERTICAL);
        root.addView(searchRow,new LinearLayout.LayoutParams(-1,dp(60)));
        EditText query = new EditText(this);
        query.setSingleLine(true);
        query.setHint("Pesquisar vídeos e canais…");
        query.setTextSize(17); query.setHintTextColor(MUTED);query.setTextColor(WHITE);
        query.setPadding(dp(18),dp(8),dp(18),dp(8));
        query.setBackground(panel(0xff14253a,false));
        searchRow.addView(query,new LinearLayout.LayoutParams(0,dp(56),1f));
        Button go = new Button(this);
        go.setText("Pesquisar");go.setTextColor(BACKGROUND);go.setAllCaps(false);
        go.setBackground(panel(CYAN,false));
        go.setOnClickListener(v -> open("search",query.getText().toString().trim()));
        LinearLayout.LayoutParams searchButton = new LinearLayout.LayoutParams(dp(170),dp(56));
        searchButton.leftMargin=dp(16);
        searchRow.addView(go,searchButton);
        pad(root, 28);

        root.addView(label("Descobre e continua", 24, WHITE, true));
        pad(root, 12);
        LinearLayout row = new LinearLayout(this);
        root.addView(row,new LinearLayout.LayoutParams(-1,-2));
        card(row,"Para ti","Descoberta personalizada",0xff175175,"home",null);
        card(row,"Inscrições","Os canais que segues",0xff174775,"subscriptions",null);
        card(row,"Biblioteca","Playlists e histórico",0xff173e66,"library",null);
        pad(root, 28);
        root.addView(label("Descobrir por tema", 24, WHITE, true));
        pad(root, 12);
        LinearLayout themes = new LinearLayout(this);
        root.addView(themes,new LinearLayout.LayoutParams(-1,-2));
        card(themes,"Música","Vídeos e artistas",0xff1b445e,"search","música");
        card(themes,"Gaming","Jogos e criadores",0xff274467,"search","gaming");
        card(themes,"Animes","Vídeos de anime",0xff244f7c,"search","animes");
    }
    private void card(LinearLayout row,String title,String desc,int color,String tab,String query) {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        view.setPadding(dp(18),dp(20),dp(16),dp(12));
        view.setGravity(Gravity.CENTER_VERTICAL);
        view.setBackground(panel(color,false));
        view.setFocusable(true);
        view.setOnFocusChangeListener((v,focus) -> {
            v.setBackground(panel(color,focus));
            v.animate().scaleX(focus?1.025f:1f).scaleY(focus?1.025f:1f).setDuration(100).start();
        });
        view.addView(label(title,21,WHITE,true));
        pad(view,7);
        view.addView(label(desc,13,MUTED,false));
        view.setOnClickListener(v -> open(tab,query));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0,dp(140),1f);
        lp.rightMargin=dp(15);
        row.addView(view,lp);
    }
    private void open(String tab,String query) {
        Intent intent = new Intent(this,MainActivity.class);
        intent.putExtra("vista_tv_section",tab);
        if(query != null && !query.isEmpty()) intent.putExtra("vista_tv_query",query);
        startActivity(intent);
    }
}
