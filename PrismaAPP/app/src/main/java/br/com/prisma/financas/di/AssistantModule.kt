package br.com.prisma.financas.di

import br.com.prisma.financas.BuildConfig
import br.com.prisma.financas.assistant.AssistantApi
import br.com.prisma.financas.assistant.AssistantConfig
import br.com.prisma.financas.assistant.AssistantLimits
import br.com.prisma.financas.assistant.QueryRunner
import br.com.prisma.financas.assistant.SqliteReadOnlyRunner
import br.com.prisma.financas.core.time.Clock
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AssistantModule {

    @Provides
    @Singleton
    fun provideAssistantConfig(): AssistantConfig =
        AssistantConfig(url = BuildConfig.ASSISTANT_URL, token = BuildConfig.ASSISTANT_TOKEN)

    @Provides
    @Singleton
    fun provideAssistantLimits(clock: Clock): AssistantLimits = AssistantLimits(clock)

    /**
     * Cliente próprio do assistente: token só neste cliente (nunca vai para a Pluggy),
     * sem log, e com tempo maior porque o modelo pode demorar.
     */
    @Provides
    @Singleton
    fun provideAssistantApi(base: OkHttpClient, config: AssistantConfig): AssistantApi {
        val client = base.newBuilder()
            .readTimeout(60, TimeUnit.SECONDS)
            .callTimeout(90, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                chain.proceed(chain.request().newBuilder().header("Authorization", "Bearer ${config.token}").build())
            }
            .build()
        val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
        return Retrofit.Builder()
            // URL inválida/ausente: usa um endereço que nunca é chamado (o orquestrador checa isConfigured antes).
            .baseUrl(config.url.takeIf { config.isConfigured } ?: "http://localhost/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(AssistantApi::class.java)
    }
}

@Module
@InstallIn(SingletonComponent::class)
abstract class AssistantBindings {
    @Binds
    abstract fun bindQueryRunner(impl: SqliteReadOnlyRunner): QueryRunner
}
